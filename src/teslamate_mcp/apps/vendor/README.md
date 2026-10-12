# Vendored front-end libraries

The map views (`drive_route.html`, `trip_route.html`, `visited_places.html`)
draw with MapLibre GL JS. The server inlines these files into the view it
serves, so nothing is loaded from a CDN.

| File | Source | Version | License |
|---|---|---|---|
| `maplibre-gl.js`, `maplibre-gl.css` | `dist/` of the [`maplibre-gl`](https://www.npmjs.com/package/maplibre-gl) npm package | 5.24.0 | BSD-3-Clause (`maplibre-gl.LICENSE.txt`) |

The 5.x line is used because its `maplibre-gl.js` is one file that starts its
own worker from a `blob:` URL; 6.x ships the worker as separate ES modules,
which a single inlined document cannot load.

To update, replace the three files from the new package and change the version
here:

```sh
npm pack maplibre-gl@<version>
tar -xzf maplibre-gl-<version>.tgz package/dist/maplibre-gl.js package/dist/maplibre-gl.css package/LICENSE.txt
```
