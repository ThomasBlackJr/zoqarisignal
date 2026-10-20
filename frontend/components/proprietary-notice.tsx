export function ProprietaryNotice({ className = "" }: { className?: string }) {
  return (
    <footer className={`proprietary-notice ${className}`}>
      © 2026 Zoqari · Signal is a proprietary product of Zoqari.
    </footer>
  );
}
