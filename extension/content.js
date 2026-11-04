function findCoverLetterField() {
  const matchingFields = new Set();

  for (const field of document.querySelectorAll("textarea")) {
    const labelTexts = [];

    // Native labels include both <label for="..."> and nested labels.
    if (field.labels) {
      for (const label of field.labels) {
        labelTexts.push(label.textContent || "");
      }
    }

    // Explicit accessible name.
    labelTexts.push(field.getAttribute("aria-label") || "");

    // Accessible name supplied by one or more referenced elements.
    const labelledBy = field.getAttribute("aria-labelledby") || "";

    for (const id of labelledBy.split(/\s+/).filter(Boolean)) {
      const referencedElement = document.getElementById(id);

      if (referencedElement) {
        labelTexts.push(referencedElement.textContent || "");
      }
    }

    const hasCoverLetterLabel = labelTexts.some((text) =>
      /\bcover[\s-]*letter\b/i.test(normaliseLabel(text))
    );

    if (hasCoverLetterLabel && isVisibleField(field)) {
      matchingFields.add(field);
    }
  }

  // Never guess if the page contains multiple matching fields.
  return matchingFields.size === 1
    ? [...matchingFields][0]
    : null;
}

function normaliseLabel(value) {
  return String(value || "")
    .normalize("NFKC")
    .toLowerCase()
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\s*\*\s*$/, "");
}

function isSupportedTextField(field) {
  if (field instanceof HTMLTextAreaElement) {
    return (
      field.getAttribute("role") !== "combobox" &&
      !field.getAttribute("aria-autocomplete") &&
      !["listbox", "option"].includes(field.getAttribute("role")) &&
      field.getAttribute("contenteditable") !== "true"
    );
  }

  if (!(field instanceof HTMLInputElement)) return false;

  const role = field.getAttribute("role");

  // Avoid custom dropdowns and autocomplete controls, even when
  // their underlying element is an ordinary text input.
  if (
    role === "combobox" ||
    role === "listbox" ||
    role === "option" ||
    field.getAttribute("aria-autocomplete") ||
    field.getAttribute("aria-haspopup") === "listbox" ||
    field.getAttribute("contenteditable") === "true"
  ) {
    return false;
  }

  return ["text", "email", "tel", "url", "search"].includes(
    field.type.toLowerCase()
  );
}

function isVisibleField(field) {
  if (!field.isConnected || field.getClientRects().length === 0) {
    return false;
  }

  const style = window.getComputedStyle(field);

  return style.display !== "none" && style.visibility !== "hidden";
}

function isEditableEmptyField(field) {
  return (
    isSupportedTextField(field) &&
    isVisibleField(field) &&
    !field.disabled &&
    !field.readOnly &&
    field.getAttribute("aria-disabled") !== "true" &&
    field.getAttribute("aria-readonly") !== "true" &&
    !field.value.trim()
  );
}

function getAccessibleLabelTexts(field) {
  const labelTexts = [];

  // Native labels, including <label for="..."> and nested labels.
  if (field.labels) {
    for (const label of field.labels) {
      labelTexts.push(label.textContent || "");
    }
  }

  // Explicit accessible name.
  labelTexts.push(field.getAttribute("aria-label") || "");

  // Accessible name supplied by referenced elements.
  const labelledBy = field.getAttribute("aria-labelledby") || "";

  for (const id of labelledBy.split(/\s+/).filter(Boolean)) {
    const referencedElement = document.getElementById(id);

    if (referencedElement) {
      labelTexts.push(referencedElement.textContent || "");
    }
  }

  return labelTexts
    .map(normaliseLabel)
    .filter(Boolean);
}

function getLabelledFields() {
  const fieldsByLabel = new Map();

  for (const field of document.querySelectorAll("input, textarea")) {
    if (!isSupportedTextField(field)) continue;

    const labels = new Set(getAccessibleLabelTexts(field));

    for (const key of labels) {
      const fields = fieldsByLabel.get(key) || new Set();
      fields.add(field);
      fieldsByLabel.set(key, fields);
    }
  }

  return fieldsByLabel;
}

function fillCandidateAnswers(candidateAnswers) {
  const result = { filled: 0, skipped: 0 };

  if (!Array.isArray(candidateAnswers)) return result;

  const fieldsByLabel = getLabelledFields();
  const answerMatches = [];

  for (const answer of candidateAnswers) {
    if (
      !answer ||
      typeof answer.question_label !== "string" ||
      typeof answer.answer !== "string" ||
      !answer.question_label.trim() ||
      !answer.answer.trim()
    ) {
      result.skipped += 1;
      continue;
    }

    const labels = [
      answer.question_label,
      ...(Array.isArray(answer.question_aliases)
        ? answer.question_aliases.filter(
            (alias) => typeof alias === "string" && alias.trim()
          )
        : []),
    ];

    const matchingFields = new Set();

    // Primary label and approved aliases are all exact-match candidates.
    // A Set prevents the same field being counted twice for one answer.
    for (const label of labels) {
      const key = normaliseLabel(label);
      if (!key) continue;

      for (const field of fieldsByLabel.get(key) || []) {
        matchingFields.add(field);
      }
    }

    // One saved answer represents one question. If it matches multiple
    // fields, do not guess which field the user intended.
    if (matchingFields.size !== 1) {
      result.skipped += 1;
      continue;
    }

    answerMatches.push({
      answer,
      field: [...matchingFields][0],
    });
  }

  const answersByField = new Map();

  for (const match of answerMatches) {
    const answers = answersByField.get(match.field) || [];
    answers.push(match);
    answersByField.set(match.field, answers);
  }

  for (const [field, matches] of answersByField) {
    // Two saved answers targeting one field are ambiguous.
    if (matches.length !== 1) {
      result.skipped += matches.length;
      continue;
    }

    if (!isEditableEmptyField(field)) {
      result.skipped += 1;
      continue;
    }

    // Preserve the exact user-authored snapshot text.
    field.value = matches[0].answer;
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.dispatchEvent(new Event("change", { bubbles: true }));

    result.filled += 1;
  }

  return result;
}

function prepareApplication(application) {
  if (!application || typeof application !== "object") {
    return {
      success: false,
      message: "Invalid application data received.",
    };
  }

  const messages = [];
  let coverLetterFilled = false;

  const coverLetter = application.cover_letter;

  if (typeof coverLetter === "string" && coverLetter.trim()) {
    const field = findCoverLetterField();

    if (!field) {
      messages.push("No clearly labelled cover-letter field was found.");
    } else if (
      field.disabled ||
      field.readOnly ||
      field.getAttribute("aria-disabled") === "true" ||
      field.getAttribute("aria-readonly") === "true"
    ) {
      messages.push("The cover-letter field is not editable.");
    } else if (field.value.trim()) {
      messages.push("The existing cover-letter text was left unchanged.");
    } else {
      field.value = coverLetter;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      field.dispatchEvent(new Event("change", { bubbles: true }));

      coverLetterFilled = true;
      messages.push("Cover letter populated.");
    }
  } else {
    messages.push("No cover letter was provided.");
  }

  const answerResult = fillCandidateAnswers(application.candidate_answers);

  messages.push(
    `${answerResult.filled} reusable answer(s) populated; ` +
    `${answerResult.skipped} skipped or unmatched.`
  );

  messages.push(
    "Review every populated field and complete the remaining fields manually. Nothing was submitted."
  );

  return {
    success: true,
    message: messages.join(" "),
    coverLetterFilled,
    candidateAnswersFilled: answerResult.filled,
    candidateAnswersSkipped: answerResult.skipped,
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "FILL_APPLICATION") return false;

  sendResponse(prepareApplication(message.application));
  return false;
});
