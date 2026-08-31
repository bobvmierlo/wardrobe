/**
 * A QR code encoder, small enough to keep in the app.
 *
 * An invitation link is a long random token: readable off a screen only by
 * typing it over, which nobody does, and long enough that a phone camera is
 * the obvious way across. That needs a QR code, and a QR code needs the full
 * URL — which only the browser knows, since the server deliberately has no
 * base-URL setting to go stale behind a reverse proxy. So it is encoded here,
 * in the one place that already knows the address it is handing out. No
 * dependency, no round trip, and it keeps working offline.
 *
 * Byte mode, error-correction level M (~15% recoverable), smallest version
 * that fits, mask chosen by the penalty rules — plain ISO/IEC 18004, so any
 * reader handles it.
 */

/** ECC codewords per block, per version, at level M. Index = version. */
const ECC_CODEWORDS_PER_BLOCK = [
  -1, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26, 30, 22, 22, 24, 24, 28, 28, 26, 26, 26,
  26, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28, 28,
];
/** Number of error-correction blocks, per version, at level M. */
const NUM_ECC_BLOCKS = [
  -1, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5, 5, 8, 9, 9, 10, 10, 11, 13, 14, 16, 17, 17, 18,
  20, 21, 23, 25, 26, 28, 29, 31, 33, 35, 37, 38, 40, 43, 45, 47, 49,
];

const MIN_VERSION = 1;
const MAX_VERSION = 40;
/** Format bits for level M, and the penalty weights, both from the standard. */
const ECC_FORMAT_BITS = 0;
const PENALTY_N1 = 3;
const PENALTY_N2 = 3;
const PENALTY_N3 = 40;
const PENALTY_N4 = 10;

/** A finished symbol: ``modules[y][x]`` is true where the module is dark. */
export interface QrMatrix {
  size: number;
  modules: boolean[][];
}

/** Total data + ECC codewords a version holds, function patterns excluded. */
function rawDataModules(version: number): number {
  let result = (16 * version + 128) * version + 64;
  if (version >= 2) {
    const numAlign = Math.floor(version / 7) + 2;
    result -= (25 * numAlign - 10) * numAlign - 55;
    if (version >= 7) result -= 36;
  }
  return result;
}

/** Codewords left for the payload once ECC has taken its share. */
function dataCodewords(version: number): number {
  return (
    Math.floor(rawDataModules(version) / 8) -
    ECC_CODEWORDS_PER_BLOCK[version] * NUM_ECC_BLOCKS[version]
  );
}

/** Where the alignment patterns sit, as coordinates on both axes. */
function alignmentPositions(version: number): number[] {
  if (version === 1) return [];
  const numAlign = Math.floor(version / 7) + 2;
  const step =
    version === 32 ? 26 : Math.ceil((version * 4 + 4) / (numAlign * 2 - 2)) * 2;
  const result = [6];
  for (let pos = version * 4 + 17 - 7; result.length < numAlign; pos -= step) {
    result.splice(1, 0, pos);
  }
  return result;
}

// ---- GF(256) arithmetic for Reed-Solomon, modulo x^8 + x^4 + x^3 + x^2 + 1 ----

function gfMultiply(x: number, y: number): number {
  let z = 0;
  for (let i = 7; i >= 0; i--) {
    z = (z << 1) ^ ((z >>> 7) * 0x11d);
    z ^= ((y >>> i) & 1) * x;
  }
  return z & 0xff;
}

/** The generator polynomial's coefficients, highest power first (monic). */
function eccDivisor(degree: number): number[] {
  const result: number[] = Array.from({ length: degree }, () => 0);
  result[degree - 1] = 1;
  let root = 1;
  for (let i = 0; i < degree; i++) {
    for (let j = 0; j < result.length; j++) {
      result[j] = gfMultiply(result[j], root);
      if (j + 1 < result.length) result[j] ^= result[j + 1];
    }
    root = gfMultiply(root, 0x02);
  }
  return result;
}

function eccRemainder(data: number[], divisor: number[]): number[] {
  const result: number[] = Array.from({ length: divisor.length }, () => 0);
  for (const b of data) {
    const factor = b ^ (result.shift() as number);
    result.push(0);
    divisor.forEach((coef, i) => {
      result[i] ^= gfMultiply(coef, factor);
    });
  }
  return result;
}

/** Split the payload into blocks, add ECC to each, and interleave the lot. */
function addEccAndInterleave(version: number, data: number[]): number[] {
  const numBlocks = NUM_ECC_BLOCKS[version];
  const blockEccLen = ECC_CODEWORDS_PER_BLOCK[version];
  const rawCodewords = Math.floor(rawDataModules(version) / 8);
  const numShortBlocks = numBlocks - (rawCodewords % numBlocks);
  const shortBlockLen = Math.floor(rawCodewords / numBlocks);

  const blocks: number[][] = [];
  const divisor = eccDivisor(blockEccLen);
  for (let i = 0, k = 0; i < numBlocks; i++) {
    const dat = data.slice(
      k,
      k + shortBlockLen - blockEccLen + (i < numShortBlocks ? 0 : 1),
    );
    k += dat.length;
    const ecc = eccRemainder(dat, divisor);
    // A short block is one byte shorter; pad it so the interleave below can
    // walk every block in step, then skip the padding again.
    if (i < numShortBlocks) dat.push(0);
    blocks.push(dat.concat(ecc));
  }

  const result: number[] = [];
  for (let i = 0; i < blocks[0].length; i++) {
    blocks.forEach((block, j) => {
      if (i !== shortBlockLen - blockEccLen || j >= numShortBlocks) result.push(block[i]);
    });
  }
  return result;
}

/** The payload as codewords: mode, length, the bytes, then the padding. */
function toCodewords(version: number, bytes: Uint8Array): number[] {
  const bits: number[] = [];
  const append = (value: number, length: number) => {
    for (let i = length - 1; i >= 0; i--) bits.push((value >>> i) & 1);
  };
  append(0b0100, 4); // byte mode
  append(bytes.length, version <= 9 ? 8 : 16);
  for (const b of bytes) append(b, 8);

  const capacity = dataCodewords(version) * 8;
  append(0, Math.min(4, capacity - bits.length)); // terminator
  append(0, (8 - (bits.length % 8)) % 8); // pad to a whole codeword
  for (let pad = 0xec; bits.length < capacity; pad ^= 0xec ^ 0x11) append(pad, 8);

  const codewords: number[] = [];
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | bits[i + j];
    codewords.push(byte);
  }
  return codewords;
}

/** Whether a module is flipped by the given mask pattern. */
function maskAt(mask: number, x: number, y: number): boolean {
  switch (mask) {
    case 0: return (x + y) % 2 === 0;
    case 1: return y % 2 === 0;
    case 2: return x % 3 === 0;
    case 3: return (x + y) % 3 === 0;
    case 4: return (Math.floor(x / 3) + Math.floor(y / 2)) % 2 === 0;
    case 5: return ((x * y) % 2) + ((x * y) % 3) === 0;
    case 6: return (((x * y) % 2) + ((x * y) % 3)) % 2 === 0;
    default: return (((x + y) % 2) + ((x * y) % 3)) % 2 === 0;
  }
}

class Symbol_ {
  readonly version: number;
  readonly size: number;
  readonly modules: boolean[][];
  /** Modules that carry the pattern rather than data: never masked. */
  private readonly isFunction: boolean[][];

  constructor(version: number) {
    this.version = version;
    this.size = version * 4 + 17;
    const blank = () =>
      Array.from({ length: this.size }, () => Array.from({ length: this.size }, () => false));
    this.modules = blank();
    this.isFunction = blank();
  }

  private set(x: number, y: number, dark: boolean) {
    this.modules[y][x] = dark;
    this.isFunction[y][x] = true;
  }

  /** Finders, separators, timing, alignment — everything but the data. */
  drawFunctionPatterns() {
    for (let i = 0; i < this.size; i++) {
      this.set(6, i, i % 2 === 0);
      this.set(i, 6, i % 2 === 0);
    }
    for (const [cx, cy] of [[3, 3], [this.size - 4, 3], [3, this.size - 4]]) {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const dist = Math.max(Math.abs(dx), Math.abs(dy));
          const x = cx + dx;
          const y = cy + dy;
          if (x >= 0 && x < this.size && y >= 0 && y < this.size) {
            this.set(x, y, dist !== 2 && dist !== 4);
          }
        }
      }
    }
    const positions = alignmentPositions(this.version);
    for (let i = 0; i < positions.length; i++) {
      for (let j = 0; j < positions.length; j++) {
        // The three corners already carry a finder pattern.
        const corner =
          (i === 0 && j === 0) ||
          (i === 0 && j === positions.length - 1) ||
          (i === positions.length - 1 && j === 0);
        if (corner) continue;
        for (let dy = -2; dy <= 2; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            this.set(
              positions[i] + dx,
              positions[j] + dy,
              Math.max(Math.abs(dx), Math.abs(dy)) !== 1,
            );
          }
        }
      }
    }
    this.drawFormatBits(0); // placeholder until the mask is chosen
    this.drawVersion();
  }

  /** The error-correction level and mask, twice, with their BCH check bits. */
  drawFormatBits(mask: number) {
    const data = (ECC_FORMAT_BITS << 3) | mask;
    let rem = data;
    for (let i = 0; i < 10; i++) rem = (rem << 1) ^ ((rem >>> 9) * 0x537);
    const bits = (((data << 10) | rem) ^ 0x5412) >>> 0;
    const bit = (i: number) => ((bits >>> i) & 1) !== 0;

    for (let i = 0; i <= 5; i++) this.set(8, i, bit(i));
    this.set(8, 7, bit(6));
    this.set(8, 8, bit(7));
    this.set(7, 8, bit(8));
    for (let i = 9; i < 15; i++) this.set(14 - i, 8, bit(i));

    for (let i = 0; i < 8; i++) this.set(this.size - 1 - i, 8, bit(i));
    for (let i = 8; i < 15; i++) this.set(8, this.size - 15 + i, bit(i));
    this.set(8, this.size - 8, true); // the module that is always dark
  }

  /** Version 7 and up spell out their version in two corners. */
  private drawVersion() {
    if (this.version < 7) return;
    let rem = this.version;
    for (let i = 0; i < 12; i++) rem = (rem << 1) ^ ((rem >>> 11) * 0x1f25);
    const bits = (this.version << 12) | rem;
    for (let i = 0; i < 18; i++) {
      const dark = ((bits >>> i) & 1) !== 0;
      const a = this.size - 11 + (i % 3);
      const b = Math.floor(i / 3);
      this.set(a, b, dark);
      this.set(b, a, dark);
    }
  }

  /** Lay the codewords into the symbol, two columns at a time, zigzagging. */
  drawCodewords(data: number[]) {
    let i = 0;
    for (let right = this.size - 1; right >= 1; right -= 2) {
      if (right === 6) right = 5; // the vertical timing pattern is not a column
      for (let vert = 0; vert < this.size; vert++) {
        for (let j = 0; j < 2; j++) {
          const x = right - j;
          const upward = ((right + 1) & 2) === 0;
          const y = upward ? this.size - 1 - vert : vert;
          if (!this.isFunction[y][x] && i < data.length * 8) {
            this.modules[y][x] = ((data[i >>> 3] >>> (7 - (i & 7))) & 1) !== 0;
            i++;
          }
        }
      }
    }
  }

  /** Apply (or, called twice with the same mask, undo) a mask pattern. */
  applyMask(mask: number) {
    for (let y = 0; y < this.size; y++) {
      for (let x = 0; x < this.size; x++) {
        if (!this.isFunction[y][x] && maskAt(mask, x, y)) {
          this.modules[y][x] = !this.modules[y][x];
        }
      }
    }
  }

  /** The four penalty rules; the mask with the lowest total wins. */
  penaltyScore(): number {
    let result = 0;
    for (const transposed of [false, true]) {
      for (let a = 0; a < this.size; a++) {
        let runColor = false;
        let runLength = 0;
        const history = [0, 0, 0, 0, 0, 0, 0];
        for (let b = 0; b < this.size; b++) {
          const dark = transposed ? this.modules[b][a] : this.modules[a][b];
          if (dark === runColor) {
            runLength++;
            if (runLength === 5) result += PENALTY_N1;
            else if (runLength > 5) result++;
          } else {
            this.addRunToHistory(runLength, history);
            if (!runColor) result += this.countFinderLike(history) * PENALTY_N3;
            runColor = dark;
            runLength = 1;
          }
        }
        result += this.terminateRun(runColor, runLength, history) * PENALTY_N3;
      }
    }
    for (let y = 0; y < this.size - 1; y++) {
      for (let x = 0; x < this.size - 1; x++) {
        const c = this.modules[y][x];
        if (
          c === this.modules[y][x + 1] &&
          c === this.modules[y + 1][x] &&
          c === this.modules[y + 1][x + 1]
        ) {
          result += PENALTY_N2;
        }
      }
    }
    let dark = 0;
    for (const row of this.modules) for (const cell of row) if (cell) dark++;
    const total = this.size * this.size;
    // How far off a 50/50 balance the symbol is, in steps of 5%.
    const k = Math.ceil(Math.abs(dark * 20 - total * 10) / total) - 1;
    return result + k * PENALTY_N4;
  }

  private addRunToHistory(runLength: number, history: number[]) {
    if (history[0] === 0) runLength += this.size; // the light border counts
    history.pop();
    history.unshift(runLength);
  }

  private terminateRun(runColor: boolean, runLength: number, history: number[]): number {
    if (runColor) {
      this.addRunToHistory(runLength, history);
      runLength = 0;
    }
    runLength += this.size; // the light border on the far side
    this.addRunToHistory(runLength, history);
    return this.countFinderLike(history);
  }

  /** The 1:1:3:1:1 pattern a reader mistakes for a finder, in either direction. */
  private countFinderLike(history: number[]): number {
    const n = history[1];
    const core =
      n > 0 &&
      history[2] === n &&
      history[3] === n * 3 &&
      history[4] === n &&
      history[5] === n;
    return (
      (core && history[0] >= n * 4 && history[6] >= n ? 1 : 0) +
      (core && history[6] >= n * 4 && history[0] >= n ? 1 : 0)
    );
  }
}

/** Encode ``text`` as a QR symbol, or throw when it is too long to fit. */
export function encodeQr(text: string): QrMatrix {
  const bytes = new TextEncoder().encode(text);
  let version = MIN_VERSION;
  for (; ; version++) {
    if (version > MAX_VERSION) throw new Error("Te lang voor een QR-code");
    const capacity = dataCodewords(version) * 8;
    if (4 + (version <= 9 ? 8 : 16) + bytes.length * 8 <= capacity) break;
  }

  const symbol = new Symbol_(version);
  symbol.drawFunctionPatterns();
  symbol.drawCodewords(addEccAndInterleave(version, toCodewords(version, bytes)));

  let bestMask = 0;
  let bestPenalty = Infinity;
  for (let mask = 0; mask < 8; mask++) {
    symbol.applyMask(mask);
    symbol.drawFormatBits(mask);
    const penalty = symbol.penaltyScore();
    if (penalty < bestPenalty) {
      bestPenalty = penalty;
      bestMask = mask;
    }
    symbol.applyMask(mask); // undo
  }
  symbol.applyMask(bestMask);
  symbol.drawFormatBits(bestMask);
  return { size: symbol.size, modules: symbol.modules };
}

/**
 * The symbol as an SVG path, drawn as one path of little squares.
 *
 * The viewBox includes the four-module quiet zone every reader expects, so the
 * caller can size the image however it likes without breaking the scan.
 */
export function qrPath(matrix: QrMatrix): { path: string; extent: number } {
  const quiet = 4;
  const parts: string[] = [];
  for (let y = 0; y < matrix.size; y++) {
    for (let x = 0; x < matrix.size; x++) {
      if (matrix.modules[y][x]) parts.push(`M${x + quiet} ${y + quiet}h1v1h-1z`);
    }
  }
  return { path: parts.join(""), extent: matrix.size + quiet * 2 };
}
