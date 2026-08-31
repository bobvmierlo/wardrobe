import { useMemo } from "react";
import { encodeQr, qrPath } from "../qr";

/**
 * An invitation link as a QR code, so the person next to you can just scan it.
 *
 * Always black on white, whatever the theme: a reader needs the contrast the
 * standard assumes, and a dark-mode QR code is one nobody can scan.
 */
export default function QrCode({
  value,
  size = 176,
  label = "QR-code van de uitnodigingslink",
}: {
  value: string;
  size?: number;
  label?: string;
}) {
  const drawing = useMemo(() => {
    try {
      return qrPath(encodeQr(value));
    } catch {
      // Only happens for a link far longer than any this app makes; better a
      // missing code than a broken one.
      return null;
    }
  }, [value]);

  if (!drawing) return null;
  return (
    <svg
      className="qr"
      width={size}
      height={size}
      viewBox={`0 0 ${drawing.extent} ${drawing.extent}`}
      role="img"
      aria-label={label}
    >
      <rect width={drawing.extent} height={drawing.extent} fill="#ffffff" />
      <path d={drawing.path} fill="#000000" />
    </svg>
  );
}
