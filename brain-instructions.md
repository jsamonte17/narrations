# Narration sound-design instructions

Use the story setting and the emotional tone of each narration paragraph to choose
quiet, supportive ambient beds. Let the sound change when the mood or scene changes;
do not put the same ambience under every paragraph by default.

Guidelines:

- For each paragraph, preserve the original words, spelling, capitalization, and word
  order exactly. The temporary TTS text may adjust punctuation only to suggest natural
  pauses and emotional delivery. Keep punctuation subtle; do not add stage directions,
  SSML, or words.
- Keep spoken narration clear; ambience should support, not overpower, the voice.
- Prefer existing reusable sound assets when they fit: `wind-gusting-soft`, `wind-gusting-hard`,
  `fire-cracking`, `waves-gentle`, `waves-crashing`, `river-flowing`,
  `crickets-chirping`, `crickets-fading`, `birds-chirping`, `rain-falling-soft`,
  `rain-falling-hard`, `rain-fading`, `ominous-low-drone`, `agimat-humming`,
  `wild-dogs-howling`, and `night-creatures`.
- A paragraph may use up to five distinct assets when the scene supports them. List
  continuous beds first, then intermittent events; keep calls, howls, and crackles
  naturally sparse. For an established quiet night, a soft wind and crickets can form
  the bed, with occasional night creatures or distant wild-dog howls only when
  plausible for the setting. Add fire only when a fire is established.
- If none of the existing assets can express an important sound in the paragraph,
  request a new composite procedural effect. Give it a short, descriptive lowercase
  hyphenated filename and combine only supported procedural layers: wind, fire, waves,
  river, crickets/birds, rain, drone, or agimat hum.
- Choose effects that fit both the location and the paragraph's emotion. For example,
  use a low drone for suspense or danger, and agimat humming for a magical moment.
- Do not add fire, rain, waves, or other specific sources unless the scene or its
  established setting supports them.
- When a paragraph describes multiple audible sources in the same scene, layer their
  matching assets together rather than selecting only one. Usually use 2-4 effects for
  a clear multi-source soundscape; use one only when the text supports one source.
  Before returning annotations, check that every explicitly described sound source
  with a matching asset is included. For example, a night paragraph mentioning a
  bonfire, sea breeze, and nearby water should include fire, wind, and gentle waves;
  add crickets as an outdoor-night bed when appropriate.
  Choose existing assets for ordinary settings; request a composite only when the scene
  calls for a distinct sound not represented by the existing library.
- Return the requested emotion, punctuation-adjusted TTS text, supported asset names,
  and supported procedural layers for each paragraph. Do not claim a procedural sound
  is a realistic recording or invent an unsupported primitive.
