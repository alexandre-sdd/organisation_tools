(() => {
  function asTrimmedString(value) {
    return typeof value === "string" ? value.trim() : "";
  }

  function normalizeStringList(value, maxItems) {
    if (!Array.isArray(value)) return [];
    const cleaned = value
      .map((item) => asTrimmedString(item))
      .filter(Boolean);
    return typeof maxItems === "number" ? cleaned.slice(0, maxItems) : cleaned;
  }

  function normalizeProfile(input) {
    const source = input && typeof input === "object" ? input : {};
    return {
      headline: asTrimmedString(source.headline),
      location: asTrimmedString(source.location),
      schools: normalizeStringList(source.schools),
      experiences: normalizeStringList(source.experiences),
      proof_points: normalizeStringList(source.proof_points, 6),
      focus_areas: normalizeStringList(source.focus_areas, 6),
      internship_goal: asTrimmedString(source.internship_goal),
      do_not_say: normalizeStringList(source.do_not_say, 12)
    };
  }

  function getEmptyProfile() {
    return normalizeProfile({});
  }

  window.LNCProfile = {
    normalizeProfile,
    getEmptyProfile
  };
})();
