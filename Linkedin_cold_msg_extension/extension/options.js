async function loadDefaults() {
  const resp = await fetch(chrome.runtime.getURL("default_profile.json"));
  return resp.json();
}

function splitLines(value) {
  return value
    .split(/\n+/)
    .map((v) => v.trim())
    .filter(Boolean);
}

function setStatus(message, isError = false) {
  const el = document.getElementById("status");
  el.textContent = message;
  el.classList.toggle("error", isError);
}

async function loadProfile() {
  return new Promise(async (resolve) => {
    chrome.storage.local.get(["my_profile"], async (res) => {
      if (res.my_profile) {
        resolve(res.my_profile);
        return;
      }
      const defaults = await loadDefaults();
      chrome.storage.local.set({ my_profile: defaults }, () => resolve(defaults));
    });
  });
}

function populateForm(profile) {
  document.getElementById("headline").value = profile.headline || "";
  document.getElementById("schools").value = (profile.schools || []).join("\n");
  document.getElementById("experiences").value = (profile.experiences || []).join("\n");
  const proof = profile.proof_points || ["", "", ""];
  document.getElementById("proof1").value = proof[0] || "";
  document.getElementById("proof2").value = proof[1] || "";
  document.getElementById("proof3").value = proof[2] || "";
  document.getElementById("tone").value = profile.tone_preference || "warm";
}

async function saveProfile() {
  const profile = {
    headline: document.getElementById("headline").value.trim(),
    schools: splitLines(document.getElementById("schools").value),
    experiences: splitLines(document.getElementById("experiences").value),
    proof_points: [
      document.getElementById("proof1").value.trim(),
      document.getElementById("proof2").value.trim(),
      document.getElementById("proof3").value.trim()
    ],
    tone_preference: document.getElementById("tone").value
  };

  chrome.storage.local.set({ my_profile: profile }, () => {
    setStatus("Saved.");
  });
}

async function init() {
  try {
    const profile = await loadProfile();
    populateForm(profile);
  } catch (err) {
    setStatus("Failed to load profile.", true);
  }

  document.getElementById("save").addEventListener("click", () => {
    saveProfile();
  });
}

init();
