function findCoverLetterField() {
  const labels = Array.from(document.querySelectorAll("label"));

  const label = labels.find((element) =>
    /cover letter/i.test(element.textContent || "")
  );

  if (!label) {
    return null;
  }

  const fieldId = label.getAttribute("for");

  if (fieldId) {
    const field = document.getElementById(fieldId);

    if (
      field instanceof HTMLTextAreaElement ||
      field instanceof HTMLInputElement
    ) {
      return field;
    }
  }

  const nestedField = label.querySelector("textarea, input");

  if (
    nestedField instanceof HTMLTextAreaElement ||
    nestedField instanceof HTMLInputElement
  ) {
    return nestedField;
  }

  return null;
}

function prepareApplication(application) {
  if (!application || typeof application !== "object") {
    return {
      success: false,
      message: "Invalid application data received.",
    };
  }

  const coverLetter = application.cover_letter;

  if (typeof coverLetter !== "string" || !coverLetter.trim()) {
    return {
      success: true,
      message: "No cover letter is available. Please complete the form manually.",
    };
  }

  const field = findCoverLetterField();

  if (!field) {
    return {
      success: true,
      message: "No clearly labelled cover-letter field was found. No fields were changed.",
    };
  }

  if (field.disabled || field.readOnly) {
    return {
      success: true,
      message: "The cover-letter field is not editable.",
    };
  }

  if (field.value.trim()) {
    return {
      success: true,
      message: "The cover-letter field already contains text. It was left unchanged.",
    };
  }

  field.value = coverLetter;

  field.dispatchEvent(new Event("input", { bubbles: true }));
  field.dispatchEvent(new Event("change", { bubbles: true }));

  return {
    success: true,
    message: "Cover letter populated. Review it and complete the remaining fields manually.",
  };
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "FILL_APPLICATION") {
    return false;
  }

  sendResponse(prepareApplication(message.application));
  return false;
});
