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

function createHarness(fields = [], referencedElements = {}) {
  const listeners = [];

  const context = {
    HTMLTextAreaElement: FakeTextArea,
    HTMLInputElement: class FakeInput {},
    Event: class FakeEvent {
      constructor(type) {
        this.type = type;
      }
    },
    document: {
      querySelectorAll(selector) {
        if (selector === "textarea") return fields;
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
    "({ findCoverLetterField, prepareApplication })",
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
