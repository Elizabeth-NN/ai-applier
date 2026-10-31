const tokenInput = document.getElementById("handoff-token");
const prepareButton = document.getElementById("prepare-button");
const status = document.getElementById("status");

prepareButton.addEventListener("click", async () => {
  const token = tokenInput.value.trim();

  if (!token) {
    status.textContent = "Please paste your handoff token first.";
    return;
  }

  prepareButton.disabled = true;
  status.textContent = "Preparing your application...";

  try {
    const result = await chrome.runtime.sendMessage({
      type: "PREPARE_APPLICATION",
      token,
    });

    if (!result?.success) {
      throw new Error(
        result?.message || result?.error || "Application preparation failed."
      );
    }

    status.textContent = result.message;
    tokenInput.value = "";
  } catch (error) {
    status.textContent =
      error.message || "Something went wrong while preparing the application.";
  } finally {
    prepareButton.disabled = false;
  }
});
