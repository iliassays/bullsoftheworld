import { useEffect, useState } from "react";
import { api, type QuizToday } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useLang } from "../lib/i18n";

// Daily quiz card on Home — gamify learning, never trading. Points and streaks measure
// understanding; the card never references any tradeable action.
export function QuizCard() {
  const { user } = useAuth();
  const { t, lang } = useLang();
  const [quiz, setQuiz] = useState<QuizToday | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!user) return;
    api.quizToday().then(setQuiz).catch(() => setQuiz(null));
  }, [user, lang]);

  if (!user || quiz === null) return null;

  const pick = async (idx: number) => {
    if (quiz.answered || busy) return;
    setBusy(true);
    try {
      setQuiz(await api.quizAnswer(quiz.question_id, idx));
    } catch {
      /* answered elsewhere or rotated — refetch the truth */
      api.quizToday().then(setQuiz).catch(() => {});
    } finally {
      setBusy(false);
    }
  };

  const choiceStyle = (idx: number) => {
    if (!quiz.answered)
      return "border-border text-text hover:border-accent";
    if (idx === quiz.answer_idx) return "border-up/60 bg-up/10 text-up font-semibold";
    if (idx === quiz.your_choice) return "border-down/60 bg-down/10 text-down";
    return "border-border text-muted opacity-60";
  };

  return (
    <div className="bg-surface border border-accent/40 rounded-2xl p-4">
      <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-muted">
        🎓 {t("quiz.title")}
        {quiz.streak > 0 && (
          <span className="normal-case tracking-normal text-accent bg-accent/10 rounded-full px-2 py-0.5">
            🔥 {quiz.streak} {t("quiz.dayStreak")}
          </span>
        )}
        <span className="ml-auto normal-case tracking-normal tnum">
          {quiz.points} {t("quiz.pts")}
        </span>
      </div>
      <div lang={lang} className="font-semibold text-sm mt-2.5 leading-snug">
        {quiz.question}
      </div>
      <div className="flex flex-col gap-2 mt-3">
        {quiz.choices.map((c, i) => (
          <button
            key={i}
            onClick={() => pick(i)}
            disabled={quiz.answered || busy}
            className={`text-left text-[13px] leading-snug border rounded-xl px-3 py-2.5 transition ${choiceStyle(i)}`}
          >
            {quiz.answered && i === quiz.answer_idx ? "✓ " : ""}
            {c}
          </button>
        ))}
      </div>
      {quiz.answered && quiz.explanation && (
        <p lang={lang} className="text-xs text-muted mt-3 leading-relaxed">
          {quiz.correct ? "✅" : "💡"} {quiz.explanation}
        </p>
      )}
      <p className="text-[10px] text-muted mt-2">{t("quiz.disclaimer")}</p>
    </div>
  );
}
