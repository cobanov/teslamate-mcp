"use strict";
/* Shared MapLibre layer for the map views (drive, trip, places): CARTO's
   vector basemap in the client's theme, zoom and fit controls, route lines,
   and HTML markers. The server inlines this and the MapLibre bundle; with
   MAP_TILES off neither is inlined and the views draw their SVG map. */
const TeslaMateMap = (() => {
  const STYLE_HOST = "__MAP_STYLE_HOST__"; // filled in by the server
  const styleUrl = (dark) =>
    STYLE_HOST + "/gl/" + (dark ? "dark-matter" : "positron") + "-gl-style/style.json";

  // MapLibre parses tiles in a worker it starts from a blob: URL. A host whose
  // CSP forbids that would leave the basemap blank, so check before using it.
  function blobWorkersAllowed() {
    return new Promise((resolve) => {
      let url = null, worker = null;
      const done = (ok) => {
        clearTimeout(timer);
        if (worker) worker.terminate();
        if (url) URL.revokeObjectURL(url);
        resolve(ok);
      };
      const timer = setTimeout(() => done(false), 2000);
      try {
        url = URL.createObjectURL(new Blob(["postMessage(1)"], { type: "text/javascript" }));
        worker = new Worker(url);
        worker.onmessage = () => done(true);
        worker.onerror = () => done(false);
      } catch (_) { done(false); }
    });
  }

  let ready = null;
  function available() {
    if (!ready) ready = typeof maplibregl === "undefined" ? Promise.resolve(false) : blobWorkersAllowed();
    return ready;
  }

  function bounds(coords) {
    const lons = coords.map((c) => c[0]), lats = coords.map((c) => c[1]);
    return [[Math.min(...lons), Math.min(...lats)], [Math.max(...lons), Math.max(...lats)]];
  }

  const ICONS = {
    plus: "M5 12h14M12 5v14",
    minus: "M5 12h14",
    fit: "M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3",
  };
  function svgEl(name, attrs) {
    const node = document.createElementNS("http://www.w3.org/2000/svg", name);
    for (const k in attrs) node.setAttribute(k, attrs[k]);
    return node;
  }
  function button(label, icon, onClick) {
    const b = document.createElement("button");
    b.type = "button";
    b.title = label;
    b.setAttribute("aria-label", label);
    const svg = svgEl("svg", {
      viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", "stroke-width": 2,
      "stroke-linecap": "round", "stroke-linejoin": "round", "aria-hidden": "true",
    });
    svg.append(svgEl("path", { d: ICONS[icon] }));
    b.append(svg);
    b.addEventListener("click", onClick);
    return b;
  }
  function group(...buttons) {
    const g = document.createElement("div");
    g.className = "tm-ctrl-group";
    g.append(...buttons);
    return g;
  }

  /* opts: dark, bounds, padding, maxZoom, fitLabel, onFail. Returns null when
     the map cannot start (no WebGL); calls onFail when the basemap cannot load. */
  function create(container, opts) {
    const fitOptions = { padding: opts.padding, maxZoom: opts.maxZoom };
    const lines = [];
    let dark = !!opts.dark, styled = false, failed = false, map;
    try {
      map = new maplibregl.Map({
        container,
        style: styleUrl(dark),
        bounds: opts.bounds,
        fitBoundsOptions: fitOptions,
        // Scrolling the conversation must not zoom the map.
        cooperativeGestures: true,
        dragRotate: false,
        pitchWithRotate: false,
        touchPitch: false,
        attributionControl: { compact: true },
      });
    } catch (err) {
      console.warn("[teslamate] MapLibre could not start:", err);
      return null;
    }
    map.touchZoomRotate.disableRotation();
    map.keyboard.disableRotation();

    const fit = () => map.fitBounds(opts.bounds, { ...fitOptions, duration: 700 });
    const controls = document.createElement("div");
    controls.className = "maplibregl-ctrl tm-ctrl";
    controls.append(
      group(button("Zoom in", "plus", () => map.zoomIn()),
            button("Zoom out", "minus", () => map.zoomOut())),
      group(button(opts.fitLabel, "fit", fit)),
    );
    map.addControl({ onAdd: () => controls, onRemove: () => controls.remove() }, "top-right");
    map.addControl(new maplibregl.ScaleControl({ maxWidth: 80 }), "bottom-left");

    // The attribution opens expanded; keep it behind its (i) button.
    const collapse = () => {
      const box = container.querySelector(".maplibregl-ctrl-attrib");
      if (box) box.classList.remove("maplibregl-compact-show");
    };
    map.on("styledata", collapse);
    map.once("idle", collapse);

    // A style change drops added layers, so the lines are drawn again after each.
    const drawLines = () => {
      const color = getComputedStyle(container).getPropertyValue("--route").trim() || "#3e6ae1";
      lines.forEach((line, i) => {
        const id = "tm-route-" + i;
        if (map.getSource(id)) return;
        map.addSource(id, {
          type: "geojson",
          data: { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: line.coordinates } },
        });
        map.addLayer({
          id, type: "line", source: id,
          layout: { "line-join": "round", "line-cap": "round" },
          paint: { "line-color": color, "line-width": line.width, "line-opacity": 0.8 },
        });
      });
    };
    map.on("style.load", () => { styled = true; drawLines(); });

    // Without the style, or the description of its tile source, there is no
    // basemap to show. A single failed tile, glyph, or sprite is not fatal.
    map.on("error", (ev) => {
      const fatal = !styled || (ev && ev.sourceId && !ev.tile);
      if (!fatal || failed) return;
      failed = true;
      console.warn("[teslamate] basemap could not load:", ev && ev.error);
      setTimeout(() => { map.remove(); opts.onFail(); }, 0);
    });

    return {
      map,
      fit,
      setDark(next) {
        if (next === dark || failed) return;
        dark = next;
        styled = false;
        map.setStyle(styleUrl(dark), { diff: false });
      },
      line(coordinates, width) {
        lines.push({ coordinates, width });
        if (styled) drawLines();
      },
      marker(lngLat, className, label) {
        const el = document.createElement("div");
        el.className = "tm-dot " + className;
        if (label) el.setAttribute("aria-label", label);
        return new maplibregl.Marker({ element: el }).setLngLat(lngLat).addTo(map);
      },
      remove() { if (!failed) map.remove(); },
    };
  }

  return { available, bounds, create };
})();
