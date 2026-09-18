# vendor/

Third-party JavaScript inlined into the map page by `build_map.py` (the
`/*__VENDOR__*/` marker in `map.template.html`). Inlined rather than loaded
from a CDN because the artifact build runs in a sandbox that blocks runtime
requests, and the site build should work offline too.

| File | Project | Version | Licence |
|---|---|---|---|
| `leaflet-1.9.4.min.js` | [Leaflet](https://leafletjs.com) — © 2010–2023 Vladimir Agafonkin, © 2010–2011 CloudMade | 1.9.4 | BSD-2-Clause |
| `leaflet.markercluster-1.5.3.min.js` | [Leaflet.markercluster](https://github.com/Leaflet/Leaflet.markercluster) — © 2012 David Leaver | 1.5.3 | MIT |

Both were fetched unmodified from cdnjs:

```
https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js
https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js
```

They power the optional **Cluster markers** view. Leaflet runs as a transparent,
non-interactive overlay synced to the canvas projection; only the cluster and
marker icons come from it. The page ships its own minimal Leaflet CSS, so
`leaflet.css` and `MarkerCluster.css` are not needed.
