# Voice and style (gifting blog, US/UK)

Details of grammar, spelling and the checking tool live in the **english-grammar-style** skill; this is the part specific to the Printerval blog.

## Voice

- Warm, specific, practical: sound like someone who knows how to choose a gift and how to personalise printed goods, not like an ad.
- Specific beats flowery: "a photo with faces filling most of the frame prints more clearly" instead of "stunning, high-quality prints".
- State drawbacks and limits plainly ("personalized items usually cannot be returned if the name is misspelled" **only when that is the real policy**).
- Sensitive occasions (bereavement, the loss of a loved one, not having children or parents): do not assume the reader's circumstances; offer gentle options.
- Do not judge the recipient or stereotype by gender or age; use inclusive language.

## US vs UK

| | US | UK |
|---|---|---|
| Spelling | color, personalized, favorite, center, gray | colour, personalised, favourite, centre, grey |
| Vocabulary | mom, sneakers, sweater, vacation, bachelorette | mum, trainers, jumper, holiday, hen do |
| Currency, dates | $; "May 9, 2027" | £; "9 May 2027" or "Sunday 9 May" |
| Units | °F, inches, lb | °C, cm, kg (miles for road distances) |
| Tone | direct; enthusiasm is acceptable | more restrained, less hype (a dense "amazing", "incredible" sounds fake) |

Choose **one** variant for the whole post (`helpful_check.py --market` reports mixing). Anchors and titles follow the same variant.

## Plain language (the basis of the readability threshold)

The US government's plain-language guidance (plainlanguage.gov) and the GOV.UK style guide both recommend short sentences, simple words, active voice, concrete examples and clear subheadings. Reference targets **[Convention]**: Flesch-Kincaid ≤ ~9-10, an average sentence of 15-20 words, paragraphs of 2-4 sentences. Printing jargon (DTG, sublimation, GSM) must be explained at first use.

## Replacements for clichés and AI-sounding phrases

| Instead of | Write |
|---|---|
| In today's fast-paced world, finding the perfect gift... | Finding a gift your grandma will use takes more than a quick search. |
| Look no further! / Unlock the power of gifting | (cut it; go straight to the first suggestion) |
| It's important to note that... | (cut it; say the important thing directly) |
| Whether you're shopping for X or Y... | Name the person: "If she reads every evening, ..." |
| Delve into / dive into / navigate the world of | cover / look at / explain |
| a rich tapestry of / seamless / robust / leverage | (use concrete words: "a wide range of", "easy", "reliable", "use") |
| In conclusion, | (end briefly, with a useful next step) |
| The ultimate / perfect gift for everyone | "A good fit if she ..., less so if ..." |

The `helpful_check.py` script counts these phrases; do not edit mechanically, re-read each sentence so that it sounds natural.

## Headings, images, formatting

- One H1; H2s built from the reader's questions and needs; do not repeat the exact keyword in every H2.
- ALT text describes the image (decorative images get `alt=""`); file names in lowercase with hyphens (see the `seo-content-vn` skill).
- A table for comparisons, a numbered list for a process, a bulleted list for items of equal rank.
- Show the author, the publish date and a real "Last updated".
