/**
 * Quiz correct-answer rules, shared by both editors and every renderer.
 * Mirrors app/services/slide_content.py (valid_quiz_answer /
 * quiz_content_error), which enforces the same rules on every save.
 */

export function isQuizContent(cj: any): boolean {
  return String(cj?.interaction_type || '').toUpperCase() === 'QUIZ' || String(cj?.mode || '').toLowerCase() === 'quiz';
}

/** The correct answer when it identifies exactly one option, else ''. Legacy
 * data may hold an answer orphaned by an option rename, and duplicate option
 * text makes an answer ambiguous — neither is ever treated as correct. */
export function validQuizAnswer(cj: any): string {
  const answer = cj?.correct_answer;
  const options = cj?.options;
  if (typeof answer !== 'string' || answer === '' || !Array.isArray(options)) return '';
  return options.filter((o: unknown) => o === answer).length === 1 ? answer : '';
}

/** Why this quiz content may not be saved, or null. The answer may stay empty
 * while it is hidden; revealing requires a valid one. A legacy record whose
 * stored answer (`existing`) was already invalid may keep it unchanged — it
 * just can't be revealed. */
export function quizSaveError(cj: any, existing?: any): string | null {
  if (!isQuizContent(cj)) return null;
  const answer = validQuizAnswer(cj);
  if (cj?.reveal_answer && !answer) return 'Mark which option is the correct answer before revealing it.';
  const stored = cj?.correct_answer;
  if (stored === undefined || stored === null || stored === '' || answer) return null;
  if (isQuizContent(existing) && stored === existing?.correct_answer && !validQuizAnswer(existing)) return null;
  return 'The correct answer must match exactly one option.';
}

/** Content for a NEW copy of a slide (duplicate): an invalid legacy answer is
 * only tolerated while unchanged on its original record, so the copy starts
 * with no answer and hidden instead. */
export function quizContentForCopy(cj: any): any {
  if (!isQuizContent(cj) || validQuizAnswer(cj)) return cj;
  return { ...cj, correct_answer: '', reveal_answer: false };
}
