(() => {
  const BUTTON_ID = "lnc-draft-btn";
  const PANEL_ID = "lnc-panel";
  const DEFAULT_PROFILE = {
    headline: "",
    schools: [],
    experiences: [],
    proof_points: ["", "", ""],
    tone_preference: "warm"
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
      let title = queryText(
        [
          ".mr1.t-bold span[aria-hidden='true']",
          ".t-16.t-bold span[aria-hidden='true']",
          ".t-bold span[aria-hidden='true']",
          "span[aria-hidden='true']"
        ],
        item
      );
      let companyLine = queryText(
        [
          ".t-14.t-normal span[aria-hidden='true']",
          ".t-14.t-normal span",
          ".t-14.t-normal",
          ".t-12.t-normal"
        ],
        item
      );
      if (!title || !companyLine) {
        const lines = collectVisibleLines(item).filter((line) => !isTimeLine(line));
        title = title || lines[0] || "";
        companyLine = companyLine || lines[1] || "";
      }
      const company = companyLine.split(" · ")[0].split("•")[0].trim();

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
    return new Promise((resolve) => {
      chrome.storage.local.get(["my_profile"], async (res) => {
        if (res.my_profile) {
          resolve(res.my_profile);
          return;
        }
        try {
          const resp = await fetch(chrome.runtime.getURL("default_profile.json"));
          const defaults = await resp.json();
          chrome.storage.local.set({ my_profile: defaults }, () => resolve(defaults));
        } catch (err) {
          resolve(DEFAULT_PROFILE);
        }
      });
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

  function generateHooks(target, myProfile) {
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
      if (hooks.length >= 3) break;
    }

    return unique(hooks).slice(0, 3);
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
        <button class="lnc-close" aria-label="Close">×</button>
      </header>
      <div class="lnc-body">
        <div class="lnc-status">Ready.</div>
        <div class="lnc-results"></div>
      </div>
    `;
    panel.querySelector(".lnc-close").addEventListener("click", () => {
      panel.style.display = "none";
    });
    document.body.appendChild(panel);
    return panel;
  }

  function setStatus(panel, message, isError = false) {
    const status = panel.querySelector(".lnc-status");
    status.textContent = message;
    status.classList.toggle("lnc-error", isError);
  }

  function renderVariants(panel, variants) {
    const container = panel.querySelector(".lnc-results");
    container.innerHTML = "";

    for (const variant of variants) {
      const card = document.createElement("div");
      card.className = "lnc-variant";
      card.innerHTML = `
        <h4>${variant.label || "variant"} · ${variant.char_count || variant.text.length} chars</h4>
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
      myProfile = (await withTimeout(ensureProfile(), 1500)) || DEFAULT_PROFILE;
    } catch (err) {
      setStatus(panel, `Profile extraction failed: ${err.message}`, true);
      return;
    }

    const hooks = generateHooks(targetProfile, myProfile);

    setStatus(panel, "Generating notes...");

    try {
      const resp = await fetch("http://localhost:8000/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          my_profile: myProfile,
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
      setStatus(panel, "Done.");
    } catch (err) {
      setStatus(panel, `Failed to generate notes: ${err.message}`, true);
    }
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
