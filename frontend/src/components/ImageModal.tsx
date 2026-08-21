import { useEffect } from "react";

/** A lightweight full-screen image viewer. Click the backdrop or press Escape
 * to close. Used to enlarge the small thumbnails on the combine screen. */
export default function ImageModal({
  src,
  alt,
  onClose,
}: {
  src: string;
  alt: string;
  onClose: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div className="img-modal" role="dialog" aria-modal="true" onClick={onClose}>
      <button type="button" className="img-modal-close" onClick={onClose} aria-label="Sluiten">
        ✕
      </button>
      <img src={src} alt={alt} onClick={(e) => e.stopPropagation()} />
    </div>
  );
}
