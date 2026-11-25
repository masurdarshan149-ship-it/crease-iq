# Crease IQ

Match forecasts for the IPL and international cricket: win chances before the match, at mid-innings and ball by ball
in a chase, par by wickets, the toss call and match previews. Learned from ball-by-ball data and tested on matches the
models never saw.

Ball-by-ball data from [Cricsheet.org](https://cricsheet.org) under the Open Data Commons Attribution License (ODC-By 1.0).
Predictions come from past data and are not a guarantee.

On a phone: open the app link, then use the browser menu → "Add to Home Screen" to install it like an app.

## Hosting

Runs on Render's free plan (render.yaml). It sleeps after 15 minutes without visitors; the next visit wakes it in
about a minute. This folder is built by scripts/publish_space.py --render on the owner's PC; edits here are replaced.
