import { LESSONS } from "../lib/lessons";

// A bottom-sheet lesson: how to actually USE a metric to decide, with a worked example.
// Descriptive education — no buy/sell.
export function LearnSheet({ lessonId, onClose }: { lessonId: string; onClose: () => void }) {
  const lesson = LESSONS[lessonId];
  if (!lesson) return null;
  const rows: { label: string; body: string }[] = [
    { label: "What it is", body: lesson.what },
    { label: "How traders use it", body: lesson.use },
    { label: "Watch out for", body: lesson.watch },
    { label: "Example", body: lesson.example },
  ];
  return (
    <div
      className="fixed inset-0 z-50 flex items-end justify-center bg-black/50"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md bg-surface border border-border rounded-t-2xl p-4 max-h-[80vh] overflow-y-auto"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="text-accent font-semibold">🎓 {lesson.title}</div>
          <button onClick={onClose} className="text-muted text-sm px-2">
            Close
          </button>
        </div>
        <div className="mt-3 flex flex-col gap-3">
          {rows.map((r) => (
            <div key={r.label}>
              <div className="text-[11px] uppercase tracking-wide text-muted">{r.label}</div>
              <p className="text-[13px] leading-snug mt-0.5">{r.body}</p>
            </div>
          ))}
        </div>
        <p className="text-[10px] text-muted mt-4">
          Educational only — not a recommendation to buy or sell.
        </p>
      </div>
    </div>
  );
}
