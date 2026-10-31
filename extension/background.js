const API_BASE_URL = "http://localhost:8000";

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message?.type !== "PREPARE_APPLICATION") {
    return false;
  }

  handlePreparation(message.token)
    .then(sendResponse)
    .catch((error) => {
      sendResponse({
        success: false,
        error: error.message || "Application preparation failed.",
        tokenConsumed: false,
      });
    });

  return true;
});

function normaliseJobUrl(value) {
  const url = new URL(value);

  if (url.protocol !== "https:") {
    return null;
  }

  return [
    url.hostname.toLowerCase(),
    url.port || "443",
    url.pathname.replace(/\/+$/, "") || "/",
    url.search,
  ].join("|");
}

async function handlePreparation(token) {
  if (typeof token !== "string" || token.trim().length < 32) {
    throw new Error("Please provide a valid handoff token.");
  }

  const tabs = await chrome.tabs.query({
    active: true,
    currentWindow: true,
  });

  const activeTab = tabs[0];

  if (!activeTab?.id || !activeTab.url) {
    throw new Error("No active browser tab was found.");
  }

  const url = new URL(activeTab.url);

  if (
    url.protocol !== "https:" ||
    !(
      url.hostname === "boards.greenhouse.io" ||
      url.hostname === "job-boards.greenhouse.io"
    )
  ) {
    throw new Error("Open a supported Greenhouse application page first.");
  }

  const response = await fetch(`${API_BASE_URL}/api/extension-handoffs/redeem`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      token: token.trim(),
      active_url: activeTab.url,
    }),
  });

  if (!response.ok) {
    if (response.status === 401) {
      throw new Error("Handoff token is invalid, expired, or already used.");
    }

    if (response.status === 409) {
      throw new Error("This token belongs to a different Greenhouse job.");
    }

    throw new Error("Could not redeem the handoff token.");
  }

  // From this point onward, the one-time token has been consumed.
  try {
    const application = await response.json();

    if (!Number.isInteger(application.execution_id)) {
      throw new Error("The backend returned an invalid application.");
    }

    if (
      application.ats_platform !== "greenhouse" ||
      normaliseJobUrl(application.target_url) !==
        normaliseJobUrl(activeTab.url)
    ) {
      throw new Error("The returned application does not match this job page.");
    }

    const result = await chrome.tabs.sendMessage(activeTab.id, {
      type: "FILL_APPLICATION",
      application,
    });

    if (!result || typeof result.success !== "boolean") {
      throw new Error("The Greenhouse page returned an invalid response.");
    }

    return {
      ...result,
      tokenConsumed: true,
    };
  } catch (error) {
    return {
      success: false,
      error: error.message || "Application preparation failed.",
      tokenConsumed: true,
    };
  }
}