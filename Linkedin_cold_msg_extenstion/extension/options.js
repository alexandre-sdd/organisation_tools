const profileApi = window.LNCProfile || {
  normalizeProfile: (input) => (input && typeof input === "object" ? input : {}),
  getEmptyProfile: () => ({
    headline: "",
    location: "",
    schools: [],
    experiences: [],
    proof_points: [],
    focus_areas: [],
    internship_goal: "",
    do_not_say: []
  })
};

async function loadDefaults() {
  const resp = await fetch(chrome.runtime.getURL("default_profile.json"));
  const raw = await resp.json();
  return profileApi.normalizeProfile(raw);
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
        const normalized = profileApi.normalizeProfile(res.my_profile);
        const changed = JSON.stringify(normalized) !== JSON.stringify(res.my_profile);
        if (changed) {
          chrome.storage.local.set({ my_profile: normalized }, () => resolve(normalized));
        } else {
          resolve(normalized);
        }
        return;
      }
      const defaults = await loadDefaults();
      chrome.storage.local.set({ my_profile: defaults }, () => resolve(defaults));
    });
  });
}

function populateForm(profile) {
  document.getElementById("headline").value = profile.headline || "";
  document.getElementById("location").value = profile.location || "";
  document.getElementById("schools").value = (profile.schools || []).join("\n");
  document.getElementById("experiences").value = (profile.experiences || []).join("\n");
  document.getElementById("proof_points").value = (profile.proof_points || []).join("\n");
  document.getElementById("focus_areas").value = (profile.focus_areas || []).join("\n");
  document.getElementById("internship_goal").value = profile.internship_goal || "";
  document.getElementById("do_not_say").value = (profile.do_not_say || []).join("\n");
}

async function saveProfile() {
  const profile = profileApi.normalizeProfile({
    headline: document.getElementById("headline").value.trim(),
    location: document.getElementById("location").value.trim(),
    schools: splitLines(document.getElementById("schools").value),
    experiences: splitLines(document.getElementById("experiences").value),
    proof_points: splitLines(document.getElementById("proof_points").value),
    focus_areas: splitLines(document.getElementById("focus_areas").value),
    internship_goal: document.getElementById("internship_goal").value.trim(),
    do_not_say: splitLines(document.getElementById("do_not_say").value)
  });

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
