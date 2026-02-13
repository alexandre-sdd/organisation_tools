(() => {
  const BUTTON_ID = "lnc-draft-btn";
  const PANEL_ID = "lnc-panel";
  const MAX_HOOKS = 3;
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
  const FALLBACK_PROFILE = profileApi.getEmptyProfile();
  const generationState = {
    targetProfile: null,
    myProfile: null,
    cycle: 0,
    isGenerating: false
  };

  const stopwords = new Set([
    "about","after","again","against","all","also","and","any","are","around","as","at","be","because","been","before","being","between","both","but","by","can","could","did","do","does","doing","down","during","each","for","from","further","had","has","have","having","he","her","here","hers","herself","him","himself","his","how","i","if","in","into","is","it","its","itself","just","me","more","most","my","myself","no","nor","not","now","of","off","on","once","only","or","other","our","ours","ourselves","out","over","own","same","she","should","so","some","such","than","that","the","their","theirs","them","themselves","then","there","these","they","this","those","through","to","too","under","until","up","very","was","we","were","what","when","where","which","while","who","whom","why","with","you","your","yours","yourself","yourselves"
  ]);

  function normalize(text) {
    return (text || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ");
  }

  function tokenize(text) {
    return normalize(text)
      .split(/\s+/)
      .map((w) => w.trim())
      .filter((w) => w.length >= 4 && !stopwords.has(w));
  }

  function unique(arr) {
    return Array.from(new Set(arr.filter(Boolean)));
  }

  function textFrom(el) {
    if (!el) return "";
    return el.textContent.replace(/\s+/g, " ").trim();
  }

  function cleanText(text) {
    return (text || "")
      .replace(/\s+/g, " ")
      .replace(/\s*See more\s*/gi, " ")
      .replace(/\s*Show more\s*/gi, " ")
      .replace(/\s*Show less\s*/gi, " ")
      .replace(/\s*…\s*$/g, "")
      .trim();
  }

  function limitText(text, maxLen) {
    if (!text) return "";
    if (text.length <= maxLen) return text;
    return `${text.slice(0, maxLen - 1).trim()}…`;
  }

  function canQuery(root) {
    return !!root && typeof root.querySelector === "function";
  }

  function queryText(selectors, root = document) {
    if (!canQuery(root)) return "";
    for (const selector of selectors) {
      const el = root.querySelector(selector);
      const text = cleanText(textFrom(el));
      if (text) return text;
    }
    return "";
  }

  function getMetaContentByProperty(prop) {
    const el = document.querySelector(`meta[property="${prop}"]`);
    return cleanText(el?.content || "");
  }

  function getMetaContentByName(name) {
    const el = document.querySelector(`meta[name="${name}"]`);
    return cleanText(el?.content || "");
  }

  function extractMetaProfile() {
    const ogTitle = getMetaContentByProperty("og:title");
    const ogDescription = getMetaContentByProperty("og:description");
    const desc = ogDescription || getMetaContentByName("description");

    const name = cleanText(ogTitle.replace(/\s*\|\s*LinkedIn.*$/i, ""));
    let headline = "";
    let location = "";

    if (desc) {
      const parts = desc.split(" | ").map((part) => cleanText(part));
      headline = parts[0] || "";
      location = parts[1] || "";
      if (/connections|followers/i.test(location)) {
        location = "";
      }
    }

    return { name, headline, location };
  }

  function findTopCardRoot() {
    const main = document.querySelector("main") || document.body;
    const h1 = main.querySelector("h1");
    if (h1) {
      return h1.closest("section") || h1.parentElement || main;
    }
    return main;
  }

  function findSectionByHeading(headingText) {
    const sections = Array.from(document.querySelectorAll("section"));
    for (const section of sections) {
      const heading = section.querySelector("h2, h3");
      if (heading && heading.textContent.toLowerCase().includes(headingText)) {
        return section;
      }
    }
    return null;
  }

  function extractAbout() {
    const aboutSection =
      document.querySelector("section#about") ||
      document.querySelector("section[aria-label*='About']") ||
      findSectionByHeading("about");

    if (!aboutSection) return "";

    const text = queryText(
      [
        ".inline-show-more-text",
        ".pv-shared-text-with-see-more",
        ".display-flex.ph5",
        ".pvs-list__item",
        "span",
        "div"
      ],
      aboutSection
    );

    return limitText(text, 700);
  }

  function collectVisibleLines(root) {
    if (!canQuery(root)) return [];
    const spans = Array.from(root.querySelectorAll("span[aria-hidden='true']"));
    return unique(spans.map((span) => cleanText(textFrom(span))).filter(Boolean));
  }

  function isTimeLine(text) {
    return /(\b\d{4}\b|present|\byrs?\b|\bmos?\b|months|years)/i.test(text) ||
      /\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)\b/i.test(text);
  }

  function normalizeKey(text) {
    return cleanText(text).toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
  }

  function isEmploymentTypeLine(text) {
    return /^(full[-\s]?time|part[-\s]?time|contract|temporary|freelance|internship|apprenticeship|self[-\s]?employed|seasonal)$/i.test(
      cleanText(text)
    );
  }

  function isLikelyMetadataLine(text) {
    return isTimeLine(text) || isEmploymentTypeLine(text);
  }

  function isContextInvalidatedError(err) {
    const message = String(err?.message || err || "").toLowerCase();
    return message.includes("extension context invalidated");
  }

  function toProfileErrorMessage(err) {
    if (isContextInvalidatedError(err)) {
      return "Extension was reloaded. Refresh this LinkedIn tab, then click Draft connection note again.";
    }
    return `Profile extraction failed: ${err?.message || "Unknown error."}`;
  }

  function extractCompanyCandidate(text) {
    return cleanText((text || "").split(" · ")[0].split("•")[0]).trim();
  }

  function isValidCompanyCandidate(company, title = "") {
    if (!company) return false;
    if (isLikelyMetadataLine(company)) return false;
    if (normalizeKey(company) === normalizeKey(title)) return false;
    return company.length >= 2;
  }

  function extractExperience() {
    const section =
      document.querySelector("section#experience") ||
      document.querySelector("section[aria-label*='Experience']") ||
      findSectionByHeading("experience");
    if (!section) return [];

    const items = Array.from(
      section.querySelectorAll(
        "li.pvs-list__item--line-separated, li.pvs-list__item, li.artdeco-list__item"
      )
    );

    const experiences = [];
    for (const item of items) {
      if (!canQuery(item)) continue;

      const visibleLines = collectVisibleLines(item);
      const structuredLines = visibleLines.filter((line) => !isLikelyMetadataLine(line));

      let title = queryText(
        [
          ".mr1.t-bold span[aria-hidden='true']",
          ".t-16.t-bold span[aria-hidden='true']",
          ".t-bold span[aria-hidden='true']",
          "span[aria-hidden='true']"
        ],
        item
      );
      if (isLikelyMetadataLine(title)) {
        title = "";
      }

      let companyLine = queryText(
        [
          ".t-14.t-normal span[aria-hidden='true']",
          ".t-14.t-normal span",
          ".t-14.t-normal",
          ".t-12.t-normal"
        ],
        item
      );
      let company = extractCompanyCandidate(companyLine);

      if (!title) {
        title = structuredLines[0] || "";
      }

      if (!company || !isValidCompanyCandidate(company, title)) {
        for (const line of structuredLines) {
          const candidate = extractCompanyCandidate(line);
          if (isValidCompanyCandidate(candidate, title)) {
            company = candidate;
            break;
          }
        }
      }

      if (!company && title && /\sat\s/i.test(title)) {
        const parts = title.split(/\sat\s/i).map((part) => cleanText(part));
        if (parts.length >= 2) {
          const maybeTitle = parts[0];
          const maybeCompany = parts.slice(1).join(" at ").trim();
          if (maybeTitle) {
            title = maybeTitle;
          }
          if (isValidCompanyCandidate(maybeCompany, title)) {
            company = maybeCompany;
          }
        }
      }

      if (title) {
        experiences.push({ title, company: company || "" });
      }
      if (experiences.length >= 2) break;
    }

    return experiences;
  }

  function extractEducation() {
    const section =
      document.querySelector("section#education") ||
      document.querySelector("section[aria-label*='Education']") ||
      findSectionByHeading("education");
    if (!section) return [];

    const item = section.querySelector(
      "li.pvs-list__item--line-separated, li.pvs-list__item, li.artdeco-list__item"
    );
    if (!item) return [];

    let school = queryText(
      [
        ".t-bold span[aria-hidden='true']",
        ".mr1.t-bold span[aria-hidden='true']",
        ".t-16.t-bold span[aria-hidden='true']",
        "span[aria-hidden='true']"
      ],
      item
    );
    if (!school) {
      const lines = collectVisibleLines(item);
      school = lines[0] || "";
    }

    return school ? [{ school }] : [];
  }

  function extractProfile() {
    const meta = extractMetaProfile();
    const root = findTopCardRoot();

    const name =
      queryText(["h1", ".pv-top-card--list > li", ".text-heading-xlarge"], root) ||
      meta.name;

    const headline =
      queryText(
        [
          ".text-body-medium.break-words",
          ".pv-text-details__left-panel .text-body-medium",
          ".text-body-medium"
        ],
        root
      ) || meta.headline;

    const location =
      queryText(
        [
          ".pv-text-details__left-panel .text-body-small.inline.t-black--light.break-words",
          ".text-body-small.inline.t-black--light.break-words",
          ".pv-text-details__left-panel .text-body-small",
          ".text-body-small"
        ],
        root
      ) || meta.location;

    const about = extractAbout();
    const top_experiences = extractExperience();
    const education = extractEducation();

    return {
      name,
      headline,
      location: location || undefined,
      about: about || undefined,
      top_experiences,
      education
    };
  }

  async function ensureProfile() {
    return new Promise((resolve, reject) => {
      try {
        chrome.storage.local.get(["my_profile"], async (res) => {
          const runtimeError = chrome.runtime?.lastError;
          if (runtimeError) {
            reject(new Error(runtimeError.message));
            return;
          }

          if (res.my_profile) {
            const normalized = profileApi.normalizeProfile(res.my_profile);
            const changed = JSON.stringify(normalized) !== JSON.stringify(res.my_profile);
            if (changed) {
              chrome.storage.local.set({ my_profile: normalized }, () => {
                const setError = chrome.runtime?.lastError;
                if (setError) {
                  reject(new Error(setError.message));
                  return;
                }
                resolve(normalized);
              });
            } else {
              resolve(normalized);
            }
            return;
          }

          try {
            const resp = await fetch(chrome.runtime.getURL("default_profile.json"));
            const defaults = await resp.json();
            const normalizedDefaults = profileApi.normalizeProfile(defaults);
            chrome.storage.local.set({ my_profile: normalizedDefaults }, () => {
              const setError = chrome.runtime?.lastError;
              if (setError) {
                reject(new Error(setError.message));
                return;
              }
              resolve(normalizedDefaults);
            });
          } catch (err) {
            if (isContextInvalidatedError(err)) {
              reject(err);
              return;
            }
            resolve(FALLBACK_PROFILE);
          }
        });
      } catch (err) {
        if (isContextInvalidatedError(err)) {
          reject(err);
          return;
        }
        resolve(FALLBACK_PROFILE);
      }
    });
  }

  function delay(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function withTimeout(promise, timeoutMs) {
    return Promise.race([promise, delay(timeoutMs).then(() => null)]);
  }

  async function waitForElement(selectors, timeoutMs = 3000) {
    const selector = Array.isArray(selectors) ? selectors.join(",") : selectors;
    const existing = document.querySelector(selector);
    if (existing) return existing;

    return new Promise((resolve) => {
      const observer = new MutationObserver(() => {
        const el = document.querySelector(selector);
        if (el) {
          observer.disconnect();
          resolve(el);
        }
      });
      observer.observe(document.documentElement, { childList: true, subtree: true });
      setTimeout(() => {
        observer.disconnect();
        resolve(null);
      }, timeoutMs);
    });
  }

  async function extractProfileWithRetry(attempts = 3) {
    for (let i = 0; i < attempts; i += 1) {
      const profile = extractProfile();
      if (profile.name || profile.headline) return profile;
      await delay(500);
    }
    return extractProfile();
  }

  async function getTargetProfile() {
    await waitForElement(["main h1", "h1.text-heading-xlarge", "h1"], 3500);
    let profile = await extractProfileWithRetry();
    if (!profile.name && !profile.headline) {
      const meta = extractMetaProfile();
      profile = {
        ...profile,
        name: profile.name || meta.name,
        headline: profile.headline || meta.headline,
        location: profile.location || meta.location
      };
    }
    return profile;
  }

  function buildHookCandidates(target, myProfile) {
    const hooks = [];
    const mySchools = (myProfile.schools || []).map((s) => s.toLowerCase());
    const myExperiences = (myProfile.experiences || []).map((s) => s.toLowerCase());

    for (const edu of target.education || []) {
      const school = edu.school || "";
      if (school && mySchools.some((s) => school.toLowerCase().includes(s))) {
        hooks.push(`Also studied at ${school}`);
      }
    }

    for (const exp of target.top_experiences || []) {
      const company = exp.company || "";
      if (company && myExperiences.some((s) => company.toLowerCase().includes(s))) {
        hooks.push(`Both have experience at ${company}`);
      }
      if (exp.title && company) {
        hooks.push(`${exp.title} at ${company}`);
      } else if (company) {
        hooks.push(`${company} experience`);
      }
    }

    const myText = [
      myProfile.headline,
      ...(myProfile.schools || []),
      ...(myProfile.experiences || [])
    ].join(" ");
    const targetText = [
      target.headline,
      target.about,
      ...(target.top_experiences || []).map((e) => `${e.title} ${e.company}`),
      ...(target.education || []).map((e) => e.school)
    ].join(" ");

    const myTokens = new Set(tokenize(myText));
    const overlap = tokenize(targetText).filter((t) => myTokens.has(t));

    for (const keyword of unique(overlap)) {
      hooks.push(`Shared interest in ${keyword}`);
    }

    return unique(hooks);
  }

  function rotateHooks(candidates, cycle, count = MAX_HOOKS) {
    const list = unique(candidates);
    if (!list.length) return [];
    const size = Math.min(count, list.length);
    const offset = ((Number(cycle) || 0) * size) % list.length;
    const rotated = [];
    for (let i = 0; i < size; i += 1) {
      rotated.push(list[(offset + i) % list.length]);
    }
    return rotated;
  }

  function generateHooks(target, myProfile, cycle = 0) {
    const candidates = buildHookCandidates(target, myProfile);
    return rotateHooks(candidates, cycle, MAX_HOOKS);
  }

  function createButton() {
    if (document.getElementById(BUTTON_ID)) return;
    const btn = document.createElement("button");
    btn.id = BUTTON_ID;
    btn.textContent = "Draft connection note";
    btn.addEventListener("click", handleClick);
    document.body.appendChild(btn);
  }

  function createPanel() {
    let panel = document.getElementById(PANEL_ID);
    if (panel) return panel;
    panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.style.display = "none";
    panel.innerHTML = `
      <header>
        <span>LinkedIn Note Copilot</span>
        <div class="lnc-header-actions">
          <button
            class="lnc-refresh"
            aria-label="Regenerate alternatives"
            title="Regenerate alternatives with different hooks"
            disabled
          >&#x21bb;</button>
          <button class="lnc-close" aria-label="Close">×</button>
        </div>
      </header>
      <div class="lnc-body">
        <div class="lnc-status">Ready.</div>
        <div class="lnc-results"></div>
      </div>
    `;
    panel.querySelector(".lnc-refresh").addEventListener("click", () => {
      regenerateAlternatives(panel);
    });
    panel.querySelector(".lnc-close").addEventListener("click", () => {
      panel.style.display = "none";
    });
    document.body.appendChild(panel);
    updateRegenerateButton(panel);
    return panel;
  }

  function setStatus(panel, message, isError = false) {
    const status = panel.querySelector(".lnc-status");
    status.textContent = message;
    status.classList.toggle("lnc-error", isError);
  }

  function updateRegenerateButton(panel) {
    const refreshBtn = panel.querySelector(".lnc-refresh");
    if (!refreshBtn) return;
    const readyToRegenerate = !!generationState.targetProfile && !!generationState.myProfile;
    refreshBtn.disabled = generationState.isGenerating || !readyToRegenerate;
  }

  function renderVariants(panel, variants) {
    const container = panel.querySelector(".lnc-results");
    container.innerHTML = "";

    const prettyLabel = (rawLabel, index) => {
      const label = String(rawLabel || "").trim().toLowerCase();
      if (label === "hook_1") return "Alternative 1";
      if (label === "hook_2") return "Alternative 2";
      if (label === "hook_3") return "Alternative 3";
      return `Alternative ${index + 1}`;
    };

    for (const [index, variant] of variants.entries()) {
      const card = document.createElement("div");
      card.className = "lnc-variant";
      card.innerHTML = `
        <h4>${prettyLabel(variant.label, index)} · ${variant.char_count || variant.text.length} chars</h4>
        <p>${variant.text}</p>
        <div class="lnc-actions">
          <button data-action="copy">Copy</button>
          <button class="secondary" data-action="insert">Insert</button>
        </div>
      `;

      card.querySelector('[data-action="copy"]').addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(variant.text);
          setStatus(panel, "Copied to clipboard.");
        } catch (err) {
          setStatus(panel, "Copy failed. Try selecting and copying manually.", true);
        }
      });

      card.querySelector('[data-action="insert"]').addEventListener("click", () => {
        const textarea = findNoteTextarea();
        if (!textarea) {
          setStatus(
            panel,
            "Open the LinkedIn connect modal and click \"Add a note\" to insert, or use Copy.",
            true
          );
          return;
        }
        textarea.focus();
        setNativeValue(textarea, variant.text);
        textarea.dispatchEvent(new Event("input", { bubbles: true }));
        setStatus(panel, "Inserted into note textarea.");
      });

      container.appendChild(card);
    }
  }

  function findNoteTextarea() {
    const selectors = [
      "textarea#custom-message",
      "textarea[name='message']",
      "textarea[aria-label*='Add a note']",
      "textarea[placeholder*='Add a note']"
    ];
    for (const selector of selectors) {
      const el = document.querySelector(selector);
      if (el && el.offsetParent !== null) return el;
    }
    return null;
  }

  function setNativeValue(element, value) {
    const descriptor = Object.getOwnPropertyDescriptor(
      Object.getPrototypeOf(element),
      "value"
    );
    if (descriptor && descriptor.set) {
      descriptor.set.call(element, value);
    } else {
      element.value = value;
    }
  }

  async function requestAlternatives(panel, targetProfile, myProfile, cycle) {
    if (generationState.isGenerating) return;

    const hooks = generateHooks(targetProfile, myProfile, cycle);
    const progress =
      cycle > 0 ? `Regenerating alternatives (${cycle + 1})...` : "Generating notes...";
    setStatus(panel, progress);

    generationState.isGenerating = true;
    updateRegenerateButton(panel);

    try {
      const resp = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          my_profile: {
            ...myProfile,
            regen_cycle: cycle
          },
          target_profile: targetProfile,
          hooks
        })
      });

      if (!resp.ok) {
        throw new Error(`Server error: ${resp.status}`);
      }

      const data = await resp.json();
      if (!data.variants || !Array.isArray(data.variants)) {
        throw new Error("Invalid response from server.");
      }

      renderVariants(panel, data.variants);
      const doneMessage = cycle > 0 ? "New alternatives generated." : "Done.";
      setStatus(panel, doneMessage);
    } catch (err) {
      setStatus(panel, `Failed to generate notes: ${err.message}`, true);
    } finally {
      generationState.isGenerating = false;
      updateRegenerateButton(panel);
    }
  }

  async function regenerateAlternatives(panel) {
    if (generationState.isGenerating) return;
    if (!generationState.targetProfile || !generationState.myProfile) {
      setStatus(panel, "Generate notes once before regenerating.", true);
      return;
    }
    generationState.cycle += 1;
    await requestAlternatives(
      panel,
      generationState.targetProfile,
      generationState.myProfile,
      generationState.cycle
    );
  }

  async function handleClick() {
    const panel = createPanel();
    panel.style.display = "block";
    setStatus(panel, "Extracting profile...");

    let targetProfile;
    let myProfile;
    try {
      targetProfile = await withTimeout(getTargetProfile(), 4500);
      if (!targetProfile) {
        throw new Error("Profile extraction timed out. Refresh the page and try again.");
      }
      if (!targetProfile.name && !targetProfile.headline) {
        throw new Error("Couldn't find profile details. Scroll to the top and try again.");
      }
      myProfile = (await withTimeout(ensureProfile(), 1500)) || FALLBACK_PROFILE;
    } catch (err) {
      setStatus(panel, toProfileErrorMessage(err), true);
      generationState.targetProfile = null;
      generationState.myProfile = null;
      generationState.cycle = 0;
      updateRegenerateButton(panel);
      return;
    }

    generationState.targetProfile = targetProfile;
    generationState.myProfile = myProfile;
    generationState.cycle = 0;
    updateRegenerateButton(panel);

    await requestAlternatives(panel, targetProfile, myProfile, generationState.cycle);
  }

  function init() {
    createButton();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
