const form = document.getElementById("scrape-form");
const statusCard = document.getElementById("status-card");
const resultCard = document.getElementById("result-card");
const statusText = document.getElementById("status-text");
const stageText = document.getElementById("stage-text");
const progressBar = document.getElementById("progress-bar");
const resultSummary = document.getElementById("result-summary");
const htmlLink = document.getElementById("html-link");
const debugLink = document.getElementById("debug-link");

let pollTimer = null;

function showStatus(message, stage, percentage) {
  statusCard.classList.remove("hidden");
  const value = Math.min(100, Math.max(0, percentage || 0));
  const label = stage || message || "";

  statusText.textContent = `${Math.round(value)}% complete`;
  stageText.textContent = label;
  progressBar.style.width = `${value}%`;
}

function showResult(data) {
  resultCard.classList.remove("hidden");
  resultSummary.textContent = `Fetched ${data.total_papers} papers.`;
  htmlLink.href = data.html_url;
  debugLink.href = data.debug_url;
}

function resetUI() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
  statusCard.classList.add("hidden");
  resultCard.classList.add("hidden");
  progressBar.style.width = "0%";
  statusText.textContent = "Waiting to start…";
  stageText.textContent = "";
}

async function startScrape(payload) {
  const response = await fetch("/api/scrape", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || "Failed to start scrape");
  }

  return response.json();
}

async function fetchStatus(jobId) {
  const response = await fetch(`/api/status/${jobId}`);
  if (!response.ok) {
    throw new Error("Failed to fetch status");
  }
  return response.json();
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  resetUI();

  const profileUrl = form.profileUrl.value.trim();
  const maxPapers = Number.parseInt(form.maxPapers.value, 10);

  showStatus("Preparing scrape…", "", 5);

  try {
    const job = await startScrape({ profile_url: profileUrl, max_papers: maxPapers });
    showStatus("Scrape scheduled", "Waiting for progress…", 10);

    pollTimer = setInterval(async () => {
      try {
        const status = await fetchStatus(job.job_id);
        showStatus(status.message, status.stage || "", status.percentage || 0);

        if (status.status === "completed") {
          clearInterval(pollTimer);
          pollTimer = null;
          showResult(status.result);
        } else if (status.status === "failed") {
          clearInterval(pollTimer);
          pollTimer = null;
          statusText.textContent = `Error: ${status.error || "Unknown failure"}`;
          stageText.textContent = "";
        }
      } catch (err) {
        console.error(err);
      }
    }, 1500);
  } catch (error) {
    statusCard.classList.remove("hidden");
    statusText.textContent = `Error: ${error.message}`;
    stageText.textContent = "";
  }
});

