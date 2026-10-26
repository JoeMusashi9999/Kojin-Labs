"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const layout = $("archive-layout");
  const viewer = $("viewer");
  const query = $("archive-search");
  const type = $("file-type");
  const sections = $("sections");
  const status = $("catalog-status");
  const preview = $("preview-shell");
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  const groups = {
    pdf: ["pdf"], spreadsheet: ["xlsx", "xls", "ods", "csv", "tsv"],
    presentation: ["pptx", "ppt", "odp"], document: ["docx", "doc", "odt", "txt", "md"],
    image: ["png", "jpg", "jpeg", "gif", "webp", "svg"],
  };
  let manifest, activeId = null, textRequest = null, activeAnimation = null;
  const records = new Map();
  const cards = new Map();

  function node(tag, text, className) {
    const element = document.createElement(tag);
    if (text !== undefined) element.textContent = text;
    if (className) element.className = className;
    return element;
  }

  function fileUrl(file) {
    const path = file.path.split("/").map(encodeURIComponent).join("/");
    return new URL("../" + path, window.location.href).href;
  }

  function fileGroup(extension) {
    return Object.keys(groups).find((key) => groups[key].includes(extension)) || "other";
  }

  function size(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }

  function date(iso) {
    return new Intl.DateTimeFormat("en", {year:"numeric", month:"short", day:"numeric", timeZone:"UTC"})
      .format(new Date(iso + "T00:00:00Z"));
  }

  function message(title, detail) {
    const element = node("div", undefined, "preview-message");
    element.append(node("strong", title), node("span", detail));
    preview.replaceChildren(element);
  }

  function renderCatalog() {
    const terms = query.value.toLocaleLowerCase().trim().split(/\s+/).filter(Boolean);
    const matching = manifest.records.filter((record) => {
      const searchable = [record.title, record.description, record.file.name,
        ...record.researchers, ...record.tags,
        manifest.sections.find((section) => section.id === record.section)?.title || ""]
        .join(" ").toLocaleLowerCase();
      return terms.every((term) => searchable.includes(term)) &&
        (type.value === "all" || fileGroup(record.file.extension) === type.value);
    });
    const fragment = document.createDocumentFragment();
    cards.clear();
    for (const section of manifest.sections) {
      const entries = matching.filter((record) => record.section === section.id);
      if (!entries.length && (terms.length || type.value !== "all")) continue;
      const container = node("section", undefined, "archive-section");
      const heading = node("div", undefined, "section-heading");
      const headingText = node("h2", section.title);
      headingText.id = "section-" + section.id.replaceAll("/", "-");
      container.setAttribute("aria-labelledby", headingText.id);
      heading.append(headingText, node("span", `${entries.length} ${entries.length === 1 ? "record" : "records"}`));
      container.append(heading, node("p", section.description, "section-description"));
      if (entries.length) {
        const grid = node("div", undefined, "file-grid");
        for (const record of entries) {
          const card = node("button", undefined, "file-card");
          card.type = "button";
          card.dataset.id = record.id;
          card.setAttribute("aria-pressed", String(record.id === activeId));
          card.setAttribute("aria-controls", "viewer");
          card.setAttribute("aria-label", `${record.title}, ${record.file.extension.toUpperCase()}, ${date(record.created)}. Open record`);
          const cover = node("span", undefined, "file-cover");
          cover.setAttribute("aria-hidden", "true");
          cover.append(node("span", record.file.extension.toUpperCase(), "file-paper"));
          const body = node("span", undefined, "file-card-body");
          body.append(node("span", record.title, "file-title"), node("span", record.description, "file-description"),
            node("span", date(record.created), "file-date"));
          card.append(cover, body);
          card.addEventListener("click", () => openRecord(record.id, card, true));
          cards.set(record.id, card);
          grid.append(card);
        }
        container.append(grid);
      } else {
        container.append(node("p", "No records published in this area yet.", "empty-section"));
      }
      fragment.append(container);
    }
    sections.replaceChildren(fragment);
    $("result-count").textContent = `${matching.length} ${matching.length === 1 ? "record" : "records"}`;
    $("clear-search").hidden = !query.value;
    status.hidden = matching.length > 0;
    if (!matching.length) status.textContent = manifest.records.length
      ? "No matching records. Try another researcher, topic, or file type."
      : "No records have been published yet.";
  }

  async function showPreview(record) {
    textRequest?.abort();
    textRequest = new AbortController();
    const signal = textRequest.signal;
    const file = record.preview || record.file;
    const url = fileUrl(file);
    const group = fileGroup(file.extension);
    if (group === "pdf") {
      const frame = node("iframe");
      frame.title = `${record.title} PDF preview`;
      frame.src = url;
      frame.setAttribute("referrerpolicy", "no-referrer");
      preview.replaceChildren(frame);
      // Browser PDF support varies. The original link is always available above.
      return;
    }
    if (group === "image") {
      const image = node("img");
      image.alt = record.title;
      image.addEventListener("error", () => {
        if (activeId === record.id) message("Preview unavailable", "Download the original to view this figure.");
      });
      image.src = url;
      preview.replaceChildren(image);
      return;
    }
    if (["txt", "md", "csv", "tsv", "json"].includes(file.extension)) {
      if (file.bytes > 250000) {
        message("Large text file", "Download the original to view the complete file.");
        return;
      }
      message("Loading preview…", "The original remains available to download.");
      try {
        const response = await fetch(url, {signal});
        if (!response.ok) throw new Error("File could not be loaded");
        const text = await response.text();
        if (activeId !== record.id || signal.aborted) return;
        // Text stays text: HTML and Markdown in archived notes cannot execute here.
        preview.replaceChildren(node("pre", text));
      } catch (error) {
        if (error.name !== "AbortError" && activeId === record.id) {
          message("Preview unavailable", "Use Download original to open this file.");
        }
      }
      return;
    }
    message(`${file.extension.toUpperCase()} original available`,
      "Download the file to open it in its native application. A PDF preview has not been included with this record.");
  }

  function addMetadata(label, value) {
    $("record-metadata").append(node("dt", label), node("dd", value));
  }

  function linkedVersion(container, label, id) {
    container.append(document.createTextNode(label));
    const button = node("button", records.get(id).title);
    button.type = "button";
    button.addEventListener("click", () => openRecord(id, null, true));
    container.append(button, document.createTextNode(". "));
  }

  function cancelAnimation() {
    if (activeAnimation) {
      activeAnimation.animation.cancel();
      activeAnimation.element.remove();
      activeAnimation = null;
    }
  }

  function animateFile(source, record) {
    cancelAnimation();
    if (!source || reducedMotion.matches || !Element.prototype.animate) return;
    const target = preview.getBoundingClientRect();
    if (target.width < 20 || source.width < 20) return;
    const sheet = node("div", undefined, "opening-sheet");
    sheet.setAttribute("aria-hidden", "true");
    sheet.append(node("small", record.file.extension.toUpperCase()), node("span", record.title));
    const width = Math.min(target.width, 330);
    const height = Math.min(target.height, 330);
    Object.assign(sheet.style, {left:`${target.left}px`, top:`${target.top}px`, width:`${width}px`, height:`${height}px`});
    document.body.append(sheet);
    const animation = sheet.animate([
      {transform:`translate(${source.left - target.left}px, ${source.top - target.top}px) scale(${source.width / width}, ${Math.min(source.height, 130) / height}) rotate(-5deg)`, opacity:.9},
      {offset:.8, transform:"translate(0, 0) scale(1) rotate(0)", opacity:.95},
      {transform:"translate(0, 0) scale(1) rotate(0)", opacity:0},
    ], {duration:650, easing:"cubic-bezier(.22,1,.36,1)"});
    const current = {element:sheet, animation};
    activeAnimation = current;
    animation.finished.catch(() => {}).finally(() => {
      sheet.remove();
      if (activeAnimation === current) activeAnimation = null;
    });
  }

  function openRecord(id, card, updateHistory) {
    const record = records.get(id);
    if (!record) return;
    const wasReading = Boolean(activeId);
    const source = card?.getBoundingClientRect();
    const tools = document.querySelector(".catalog-tools");
    const searchBefore = tools.getBoundingClientRect();
    activeId = id;
    viewer.hidden = false;
    layout.classList.add("is-reading");
    viewer.classList.add("is-visible");
    $("record-title").textContent = record.title;
    $("record-description").textContent = record.description;
    $("record-metadata").replaceChildren();
    addMetadata("Created", date(record.created));
    addMetadata("Researchers", record.researchers.join(", ") || "Not specified");
    addMetadata("File", `${record.file.name} · ${size(record.file.bytes)}`);
    addMetadata("Topics", record.tags.join(", ") || "None listed");
    const download = $("download-record");
    download.href = fileUrl(record.file);
    download.download = record.file.name;
    $("github-record").hidden = !record.source_commit;
    if (record.source_commit) $("github-record").href = record.source_commit;
    $("source-record").hidden = !record.source_url;
    if (record.source_url) $("source-record").href = record.source_url;
    $("record-hash").textContent = record.file.sha256;
    $("archive-revision").textContent = manifest.revision ? `Publication commit: ${manifest.revision}` : "Local preview. Commit identity is added when published.";
    const versionNote = $("version-note");
    versionNote.replaceChildren();
    if (record.supersedes && records.has(record.supersedes)) linkedVersion(versionNote, "Updates: ", record.supersedes);
    for (const newer of manifest.records.filter((entry) => entry.supersedes === record.id)) linkedVersion(versionNote, "Later version: ", newer.id);
    versionNote.hidden = !versionNote.childNodes.length;
    for (const [key, button] of cards) button.setAttribute("aria-pressed", String(key === id));
    showPreview(record);
    if (updateHistory) {
      history.pushState(null, "", "#" + encodeURIComponent(id));
      $("record-title").focus({preventScroll:true});
    }
    if (!wasReading && !reducedMotion.matches && Element.prototype.animate) {
      const searchAfter = tools.getBoundingClientRect();
      tools.animate([
        {transform:`translateX(${searchBefore.left - searchAfter.left}px)`, width:`${searchBefore.width}px`},
        {transform:"translateX(0)", width:`${searchAfter.width}px`},
      ], {duration:550, easing:"cubic-bezier(.22,1,.36,1)"});
      viewer.animate([{opacity:0, transform:"translateY(18px)"}, {opacity:1, transform:"translateY(0)"}], {duration:450});
    }
    requestAnimationFrame(() => {
      // A quick second selection should never animate a stale record.
      if (activeId !== id) return;
      animateFile(source, record);
      if (updateHistory && window.matchMedia("(max-width: 800px)").matches) viewer.scrollIntoView({behavior:reducedMotion.matches ? "instant" : "smooth", block:"start"});
    });
  }

  function closeRecord(updateHistory) {
    const old = activeId;
    activeId = null;
    textRequest?.abort();
    cancelAnimation();
    layout.classList.remove("is-reading");
    viewer.classList.remove("is-visible");
    viewer.hidden = true;
    preview.replaceChildren();
    for (const button of cards.values()) button.setAttribute("aria-pressed", "false");
    if (updateHistory) {
      history.pushState(null, "", location.pathname + location.search);
      (cards.get(old) || query).focus({preventScroll:true});
    }
  }

  function readHash() {
    let id;
    try { id = decodeURIComponent(location.hash.slice(1)); } catch { return; }
    if (records.has(id)) openRecord(id, null, false);
    else closeRecord(false);
  }

  query.addEventListener("input", () => manifest && renderCatalog());
  type.addEventListener("change", () => manifest && renderCatalog());
  $("clear-search").addEventListener("click", () => {query.value=""; renderCatalog(); query.focus();});
  $("close-record").addEventListener("click", () => closeRecord(true));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && activeId) {event.preventDefault(); closeRecord(true);}
  });
  window.addEventListener("popstate", () => manifest && readHash());
  window.addEventListener("hashchange", () => manifest && readHash());

  async function init() {
    try {
      const response = await fetch("manifest.json");
      if (!response.ok) throw new Error("Manifest unavailable");
      manifest = await response.json();
      if (manifest.schema_version !== 1 || !Array.isArray(manifest.records) || !Array.isArray(manifest.sections)) throw new Error("Invalid manifest");
      manifest.records.forEach((record) => records.set(record.id, record));
      renderCatalog();
      readHash();
    } catch (error) {
      manifest = null;
      status.hidden = false;
      status.textContent = "The archive could not be loaded. Refresh the page, or browse the archive-content folder on GitHub.";
      $("result-count").textContent = "Archive unavailable";
    }
  }
  init();
})();
