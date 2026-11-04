const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const contentScript = fs.readFileSync(
  path.join(__dirname, "..", "content.js"),
  "utf8"
);

class FakeTextArea {
  constructor(attributes = {}) {
    this.attributes = attributes;
    this.labels = [];
    this.value = "";
    this.disabled = false;
    this.readOnly = false;
    this.isConnected = true;
    this.events = [];
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  getClientRects() {
    return this.isConnected ? [{}] : [];
  }

  dispatchEvent(event) {
    this.events.push(event.type);
    return true;
  }
}

class FakeInput {
  constructor(attributes = {}) {
    this.attributes = attributes;
    this.labels = [];
    this.value = "";
    this.disabled = false;
    this.readOnly = false;
    this.isConnected = true;
    this.events = [];
    this.type = attributes.type || "text";
  }

  getAttribute(name) {
    return this.attributes[name] ?? null;
  }

  getClientRects() {
    return this.isConnected ? [{}] : [];
  }

  dispatchEvent(event) {
    this.events.push(event.type);
    return true;
  }
}

function createHarness(fields = [], referencedElements = {}) {
  const listeners = [];

  const context = {
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: FakeInput,
    Event: class FakeEvent {
      constructor(type) {
        this.type = type;
      }
    },
    document: {
      querySelectorAll(selector) {
        if (selector === "textarea") {
          return fields.filter((field) => field instanceof FakeTextArea);
        }

        if (selector === "input, textarea") return fields;
        if (selector === "label") return [];
        return [];
      },
      getElementById(id) {
        return referencedElements[id] || null;
      },
    },
    window: {
      getComputedStyle() {
        return { display: "block", visibility: "visible" };
      },
    },
    chrome: {
      runtime: {
        onMessage: {
          addListener(listener) {
            listeners.push(listener);
          },
        },
      },
    },
  };

  vm.createContext(context);
  vm.runInContext(contentScript, context);

  return vm.runInContext(
    "({ findCoverLetterField, fillCandidateAnswers, prepareApplication })",
    context
  );
}

test("finds a textarea through its native label", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Cover Letter" }];

  const { findCoverLetterField } = createHarness([field]);

  assert.equal(findCoverLetterField(), field);
});

test("finds a textarea through aria-label", () => {
  const field = new FakeTextArea({
    "aria-label": "Cover Letter",
  });

  const { findCoverLetterField } = createHarness([field]);

  assert.equal(findCoverLetterField(), field);
});

test("finds a textarea through aria-labelledby", () => {
  const field = new FakeTextArea({
    "aria-labelledby": "cover-letter-heading",
  });

  const heading = { textContent: "Cover Letter" };

  const { findCoverLetterField } = createHarness(
    [field],
    { "cover-letter-heading": heading }
  );

  assert.equal(findCoverLetterField(), field);
});

test("does not select a textarea without an explicit cover-letter label", () => {
  const field = new FakeTextArea({
    placeholder: "Write your cover letter",
  });

  const { findCoverLetterField } = createHarness([field]);

  assert.equal(findCoverLetterField(), null);
});

test("does not select a hidden cover-letter textarea", () => {
  const field = new FakeTextArea({
    "aria-label": "Cover Letter",
  });
  field.isConnected = false;

  const { findCoverLetterField } = createHarness([field]);

  assert.equal(findCoverLetterField(), null);
});

test("refuses to choose when multiple visible cover-letter fields match", () => {
  const first = new FakeTextArea({ "aria-label": "Cover Letter" });
  const second = new FakeTextArea();
  second.labels = [{ textContent: "Cover Letter" }];

  const { findCoverLetterField } = createHarness([first, second]);

  assert.equal(findCoverLetterField(), null);
});

test("fills an empty cover-letter field", () => {
  const field = new FakeTextArea({
    "aria-label": "Cover Letter",
  });

  const { prepareApplication } = createHarness([field]);
  const result = prepareApplication({
    cover_letter: "Dear Hiring Manager,",
  });

  assert.equal(field.value, "Dear Hiring Manager,");
  assert.deepEqual(field.events, ["input", "change"]);
  assert.equal(result.coverLetterFilled, true);
});

test("does not overwrite existing cover-letter text", () => {
  const field = new FakeTextArea({
    "aria-label": "Cover Letter",
  });
  field.value = "My existing text";

  const { prepareApplication } = createHarness([field]);
  const result = prepareApplication({
    cover_letter: "New cover letter",
  });

  assert.equal(field.value, "My existing text");
  assert.equal(result.coverLetterFilled, false);
  assert.match(result.message, /existing cover-letter text was left unchanged/i);
});


test("fills a candidate answer using its exact primary question label", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Tell us about your experience with Python.*" }];

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Tell us about your experience with Python.",
      question_aliases: [],
      answer: "I use Python for backend development.",
    },
  ]);

  assert.equal(field.value, "I use Python for backend development.");
  assert.deepEqual(field.events, ["input", "change"]);
  assert.equal(result.filled, 1);
  assert.equal(result.skipped, 0);
});

test("fills a candidate answer using an approved exact question alias", () => {
  const field = new FakeTextArea();
  field.labels = [
    {
      textContent:
        "Briefly describe your Python software development experience.*",
    },
  ];

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Tell us about your experience with Python.",
      question_aliases: [
        "Briefly describe your Python software development experience.",
      ],
      answer: "I use Python to build backend applications and APIs.",
    },
  ]);

  assert.equal(
    field.value,
    "I use Python to build backend applications and APIs."
  );
  assert.equal(result.filled, 1);
  assert.equal(result.skipped, 0);
});

test("matches accessible aria-label text for candidate answers", () => {
  const field = new FakeInput({
    "aria-label": "Describe your experience with Python",
  });

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Describe your experience with Python",
      answer: "I build backend applications with Python.",
    },
  ]);

  assert.equal(field.value, "I build backend applications with Python.");
  assert.equal(result.filled, 1);
});

test("matches candidate-answer labels supplied through aria-labelledby", () => {
  const field = new FakeTextArea({
    "aria-labelledby": "python-question",
  });

  const { fillCandidateAnswers } = createHarness(
    [field],
    {
      "python-question": {
        textContent: "Describe your Python experience",
      },
    }
  );

  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "I use Python for backend development.",
    },
  ]);

  assert.equal(field.value, "I use Python for backend development.");
  assert.equal(result.filled, 1);
});

test("does not fill a partial question-label match", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Tell us about your experience with Python" }];

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Tell us about your experience",
      answer: "Some answer",
    },
  ]);

  assert.equal(field.value, "");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 1);
});

test("does not fill when one answer matches multiple fields", () => {
  const first = new FakeTextArea();
  first.labels = [{ textContent: "Describe your Python experience" }];

  const second = new FakeTextArea();
  second.labels = [{ textContent: "Describe your Python experience" }];

  const { fillCandidateAnswers } = createHarness([first, second]);
  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "Some answer",
    },
  ]);

  assert.equal(first.value, "");
  assert.equal(second.value, "");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 1);
});

test("does not fill when two answers target the same field", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Describe your Python experience" }];

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "First answer",
    },
    {
      question_label: "Another question",
      question_aliases: ["Describe your Python experience"],
      answer: "Second answer",
    },
  ]);

  assert.equal(field.value, "");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 2);
});

test("does not fill custom dropdown or autocomplete inputs", () => {
  const dropdown = new FakeInput({
    role: "combobox",
    "aria-label": "Describe your Python experience",
  });

  const autocomplete = new FakeInput({
    "aria-autocomplete": "list",
    "aria-label": "Describe your Python experience",
  });

  const { fillCandidateAnswers } = createHarness([
    dropdown,
    autocomplete,
  ]);

  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "Some answer",
    },
  ]);

  assert.equal(dropdown.value, "");
  assert.equal(autocomplete.value, "");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 1);
});

test("does not overwrite existing candidate-answer values", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Describe your Python experience" }];
  field.value = "My existing response";

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "New response",
    },
  ]);

  assert.equal(field.value, "My existing response");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 1);
});

test("does not fill disabled candidate-answer fields", () => {
  const field = new FakeTextArea();
  field.labels = [{ textContent: "Describe your Python experience" }];
  field.disabled = true;

  const { fillCandidateAnswers } = createHarness([field]);
  const result = fillCandidateAnswers([
    {
      question_label: "Describe your Python experience",
      answer: "Some answer",
    },
  ]);

  assert.equal(field.value, "");
  assert.equal(result.filled, 0);
  assert.equal(result.skipped, 1);
});
