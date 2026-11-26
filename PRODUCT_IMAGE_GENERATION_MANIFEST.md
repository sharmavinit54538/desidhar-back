# DesiDhar Product Photography & Image Generation Manifest

> **Generated:** 2026-11-26  
> **Catalog Coverage:** 12 / 12 Active Products (4 Categories: `Milk`, `Ghee and Butter`, `Paneer and Cream`, `Sweets`)  
> **Served Assets:** 44 Unique Multi-Angle Shots × 4 Responsive WebP Sizes (`320`, `640`, `1200`/`1600`, `2048` px · sRGB · `1:1`) = **176 Optimized WebP Files** (`18.61 MB` total)  
> **Original Image Backup Location:** `backend/desidhar-back/app/static/products/_originals_backup/` (22 clean historical `.jpg` assets archived before updates; original root `.jpg` paths preserved for historical order snapshots)

---

## 1. Execution Status Summary

| Category | Count | Source Method | Status |
| :--- | :---: | :--- | :--- |
| **AI-Generated Commercial Studio Photos** | **24 shots** | `image-generator` (DSLR 1:1 studio) | Integrated (`gulab-jamun` 01–04, `rasgulla` 01–04, `kaju-katli` 01–04, `butter` 01–05, `pure-desi-ghee` 01, `white-butter-makhan` 01–06) |
| **Verified Reference-Enhanced Studio Photos** | **20 shots** | Verified product reference photos processed with sRGB conversion, white-balance normalization, spot-healing (`raw_desi_makhan`, `raw_cow_milk`), and multi-resolution Lanczos WebP encoding | Integrated across remaining slots (`gulab-jamun` 05, `pure-desi-ghee` 02–04, `white-butter-makhan` 07, `fresh-paneer` 01–03, `malai-paneer` 01–03, `fresh-cream` 01–02, `full-cream-milk` 01–02, `toned-milk` 01–02, `cow-milk` 01–03) |
| **Pending AI Studio Regeneration Queue** | **57 shots** | Blocked by `HTTP 429 RESOURCE_EXHAUSTED` quota reset (`~4h28m51s` remaining verified at `2026-11-26 10:45 IST`) | Ready-to-run prompts documented in **Section 3** (`white-butter-makhan` 4 scenes, `malai-paneer` 10 scenes, `fresh-paneer` 10 scenes, plus sweets/dairy backlog) |

---

## 2. Catalog Audit, Asset Mapping & Optimization Metrics

All product URLs in PostgreSQL `product_images` (`44` rows across `12` SKUs) resolve to verified `-1200.webp` or `-1600.webp` catalog assets served identically from `backend/desidhar-back/app/static/products/<slug>/` and `desidhar-api-integration/public/static/products/<slug>/`. Responsive `srcSet` (`320w`, `640w`, `1200w`/`1600w`, `2048w`) is derived client-side.

| Slug | Product (Pack Size) | Old DB Mapping (Issues Found) | Integrated Shots (Count & Origin) | 320px Card Sum | Primary Detail Sum | 2048px Master Sum |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: |
| `gulab-jamun` | Gulab Jamun (`1.00 kg`) | `product-milk-cake.jpg` (Wrong sweet), `product-photo-sheet.jpg` (Collage) | **5:** `01-primary-white` (AI), `02-lifestyle` (AI), `03-closeup-macro` (AI), `04-angle` (AI), `05-served-bowl` (`raw_gulab_jamun.jpg`) | 96.7 KB | 739.5 KB | 1.36 MB |
| `rasgulla` | Rasgulla (`1.00 kg`) | `product-burfi.jpg` (Wrong sweet) | **4:** `01-primary-white` (AI), `02-lifestyle` (AI), `03-closeup-macro` (AI), `04-angle` (AI) | 48.7 KB | 326.2 KB | 652.3 KB |
| `kaju-katli` | Kaju Katli (`500.00 g`) | `product-burfi.jpg` (Wrong sweet) | **4:** `01-primary-white` (AI), `02-lifestyle` (AI), `03-closeup-macro` (AI), `04-angle` (AI) | 82.8 KB | 709.6 KB | 1.31 MB |
| `pure-desi-ghee` | Pure Desi Ghee (`1.00 kg`) | `product-ghee.jpg`, `story-churning.jpg` (512px low-res primary) | **4:** `01-primary-white` (AI), `02-spoon-drip` (`product-ghee.jpg`), `03-closeup-texture` (AI macro), `04-traditional-bilona` (`story-churning.jpg`) | 68.6 KB | 429.0 KB | 813.7 KB |
| `butter` | Butter (`500.00 g`) | `product-ghee.jpg` (Wrong product) | **5:** `01-primary-white` (AI), `02-lifestyle` (AI), `03-closeup-macro` (AI), `04-angle` (AI), `05-usage` (AI) | 88.0 KB | 541.2 KB | 1.05 MB |
| `white-butter-makhan` | White Butter (Makhan) (`250.00 g`) | `product-ghee.jpg` (Wrong product) | **7:** `01-ceramic-cream-studio` (AI), `02-terracotta-wooden-table` (AI), `03-creamy-texture-macro` (AI), `04-overhead-steel-bowl` (AI), `05-dark-slate-studio` (AI), `06-wooden-spoon-scoop` (AI), `07-handrolled-porcelain-bowl` (`raw_desi_makhan.jpg`) | 104.8 KB | 1.39 MB (`1600px`) | 1.62 MB |
| `fresh-paneer` | Fresh Paneer (`500.00 g`) | `product-dahi.jpg`, `product-photo-sheet.jpg` (Wrong dairy item + collage) | **3:** `01-plate-cubes` (`raw_paneer_cubes.jpg` WB-normalized), `02-diced-cubes` (`raw_paneer_block.jpg`), `03-closeup-texture` | 39.0 KB | 288.6 KB | 562.7 KB |
| `malai-paneer` | Malai Paneer (`500.00 g`) | `product-mava.jpg` (Wrong dairy item) | **3:** `01-artisan-slab` (`raw_malai_paneer.jpg` WB-normalized), `02-cubes-and-cut`, `03-closeup-texture` | 119.6 KB | 1.07 MB | 1.81 MB |
| `fresh-cream` | Fresh Cream (`250.00 ml`) | `product-dahi.jpg` (Wrong image despite `product-fresh-cream.jpg` on disk) | **2:** `01-ceramic-bowl` (`product-fresh-cream.jpg`), `02-closeup-swirl` | 22.3 KB | 108.3 KB | 196.4 KB |
| `full-cream-milk` | Full Cream Milk (`1.00 litre`) | `product-milk.jpg`, `product-photo-sheet.jpg` (Collage on gallery slide 2) | **2:** `01-carafe-pour` (`product-milk.jpg`), `02-closeup-glass` | 12.2 KB | 58.1 KB | 105.7 KB |
| `toned-milk` | Toned Milk (`1.00 litre`) | `product-milk.jpg` (Duplicate of Full Cream despite `product-toned-milk.jpg` on disk) | **2:** `01-tall-glass` (`product-toned-milk.jpg`), `02-rim-closeup` | 10.3 KB | 51.5 KB | 93.4 KB |
| `cow-milk` | Cow Milk (`500.00 ml`) | `product-milk.jpg` (Duplicate) | **3:** `01-studio-glass` (`raw_cow_milk.jpg` speck-healed), `02-classic-glass` (`raw_milk_001.jpg`), `03-rim-closeup` | 29.0 KB | 405.3 KB | 818.4 KB |

> **Skipped Low-Quality References (Visual QA):** `raw_rasgulla.jpg` (visible newspaper & table pebbles), `raw_kaju_katli.jpg` (glaring yellow plastic bowl), and `raw_paneer_2.jpg` (cooked tomato gravy dish, not raw paneer block) were intentionally excluded so misleading or amateur imagery never reaches the storefront.

---

## 3. Ready-to-Run AI Photography Manifest (Blocked by HTTP 429 Quota)

When image generation quota resets, run these exact DSLR-style prompts (`1:1`, `sRGB`, `2048×2048` target) and review outputs alongside existing shots before replacing any database entries.

### Universal Negative Prompt (Apply to All Shots Below)
```text
cartoon, illustration, 3D render, CGI, plastic food, oversaturated colors, floating object, unrealistic cast shadows, watermarks, fake FSSAI/organic badges, invented labels, misspelled brand text, blurry details, duplicate framing, stock photo cliché.
```

---

### A. Partial AI Sets — Missing Usage / Studio Shots (7 Shots)

1. **`gulab-jamun` — Shot 05 (Product Usage / Festive Serving)**
   - **Reference:** `raw_gulab_jamun.jpg`, `gulab-jamun-02-lifestyle`
   - **Prompt:** *Overhead 3/4 editorial food photograph of warm Indian Gulab Jamun served in small brass katori bowls with a silver spoon scooping one syrup-soaked jamun topped with pistachio slivers, dark roasted walnut wood table, warm candlelight bokeh, shallow depth of field, 50mm f/2.2 DSLR commercial quality.*

2. **`rasgulla` — Shot 05 (Product Usage / Serving Moment)**
   - **Reference:** `rasgulla-01-primary-white`
   - **Prompt:** *Realistic editorial Indian dessert photograph of two chilled white spongy Rasgullas served in a small handmade porcelain katori being gently halved with a clean silver dessert spoon, revealing airy syrup-filled chena interior, linen napkin and soft morning window light, DSLR studio food photography.*

3. **`kaju-katli` — Shot 05 (Product Usage / Gift Box Presentation)**
   - **Reference:** `kaju-katli-01-primary-white`
   - **Prompt:** *Authentic editorial photograph of fresh silver-varq diamond Kaju Katli pieces arranged neatly inside an open unbranded ivory butter-paper lined rigid sweet box beside a ceramic plate with two pieces and whole roasted cashews, soft natural window lighting, high-end Indian mithai photography.*

4. **`pure-desi-ghee` — Shot 02 (Premium Lifestyle)**
   - **Reference:** `pure-desi-ghee-01-primary-white`
   - **Prompt:** *Commercial lifestyle food photograph of an unlabelled clear glass jar of golden granular bilona cow desi ghee on a warm sandstone countertop beside fresh wheat rotis in a brass thali and an earthen diya silhouette in soft background blur, warm morning sunlight, DSLR 50mm f/2.4.*

5. **`pure-desi-ghee` — Shot 03 (Close-Up Macro Texture)**
   - **Prompt:** *Extreme macro studio photograph of rich golden danedar cow desi ghee glistening on a brushed stainless spoon held above the glass jar rim, sharp crystalline grain texture, natural warm specular highlights, shallow depth of field, DSLR 100mm macro lens.*

6. **`pure-desi-ghee` — Shot 04 (45° Side Angle)**
   - **Reference:** `pure-desi-ghee-01-primary-white`
   - **Prompt:** *Studio product photograph at a clean 45-degree angle of an open wide-mouth glass jar filled with golden bilona desi ghee and brushed metal cap resting alongside on a soft light warm-grey studio surface with subtle contact shadow, crisp glass refraction, 85mm studio lens.*

7. **`pure-desi-ghee` — Shot 05 (Product Usage / Pouring Over Hot Tawa Roti)**
   - **Prompt:** *Realistic Indian home kitchen usage photograph: a stainless spoon pouring melted golden pure desi ghee onto a freshly puffed hot phulka roti in a brass plate, gentle steam wisping, natural warm side light, zero brand logos or claims, authentic culinary photography.*

---

### B. Dairy, Butter, Cream, Paneer & Milk SKUs (35 Remaining Shots — Butter 5/5 Already Complete)

#### `butter` (Butter · 500 g — **5/5 Unbranded Studio Photos Integrated**)
- All 5 studio views (`01-primary-white`, `02-lifestyle`, `03-closeup-macro`, `04-angle`, `05-usage`) generated and active under `/static/products/butter/`. No further prompts needed.

#### `white-butter-makhan` (White Butter Makhan · 250 g — **7/10 Live (`1600px` `160–249 KB`), 4 Blocked by HTTP 429**)
- **Already Live (AI DSLR + Verified Ref):** `01-ceramic-cream-studio`, `02-terracotta-wooden-table`, `03-creamy-texture-macro`, `04-overhead-steel-bowl`, `05-dark-slate-studio`, `06-wooden-spoon-scoop`, `07-handrolled-porcelain-bowl`.
- **Blocked Shot — Paratha Serving:** *Appetizing Indian breakfast photograph showing two generous scoops of snowy-white artisanal white makhan softening and melting naturally over a golden crispy tandoori stuffed aloo paratha plated on speckled stoneware with faint natural warmth/steam, never yellow commercial butter, DSLR 50mm f/2.8.*
- **Blocked Shot — Traditional Kitchen Utensils:** *Traditional Indian kitchen counter scene featuring whipped white makhan in a hammered white-lined brass katori bowl surrounded cleanly by vintage clean brass/copper katoris, stainless spoon, and folded linen cotton cloth in soft daylight.*
- **Blocked Shot — Indian Breakfast Table:** *Authentic North Indian morning breakfast table: snowy-white makhan in a fluted porcelain bowl in the foreground alongside freshly puffed tawa phulka rotis and crisp layered triangular parathas on an oak tray, warm window light.*
- **Blocked Shot — Natural Morning Sunlight Lifestyle:** *Soft ivory-white makhan inside an earthy hand-thrown ceramic bowl resting near a sunlit window in a traditional Indian home kitchen bathed in warm golden early-morning window sunbeams casting delicate shadows across wood and linen.*

#### `fresh-cream` (Fresh Cream · 250 ml · **Reference: `product-fresh-cream.jpg`**)
- **Shot 01 (Primary White):** *Pure `#FFFFFF` studio photograph of thick, velvety fresh dairy malai cream with a soft swirled center peak in a matte stoneware bowl, soft natural studio contact shadow, neutral pure cream white tone.*
- **Shot 02 (Lifestyle):** *Artisanal speckled ceramic bowl of rich chilled fresh cream resting on cool limestone beside a small glass pitcher and fresh berries/mint leaf accent cleanly placed to the side, soft diffused daylight.*
- **Shot 03 (Macro Texture):** *Extreme 100mm macro shot of silky whipped dairy cream ripples catching soft studio specular highlights without plastic gloss.*
- **Shot 04 (45° Angle):** *45-degree studio photograph of fresh cream poured gracefully from a clear glass creamer into a shallow ceramic bowl on neutral light studio surface.*
- **Shot 05 (Usage):** *Finishing drizzle of rich fresh cream from a metal spoon over slow-simmered paneer makhani in a copper kadai, warm natural kitchen photography.*

#### `fresh-paneer` (Fresh Paneer · 500 g · **Target Filenames `fresh-paneer-01.webp`..`fresh-paneer-10.webp` (`1600×1600`, `150–300 KB`) — Blocked by HTTP 429 Quota Reset `~4h28m51s`**)
> *Current gallery retains white-balanced reference renders (`raw_paneer_cubes.jpg` & `raw_paneer_block.jpg`). All 10 bespoke independent DSLR prompts below distinguish firm, clean-cut, slightly porous moist **Fresh Paneer** from extra-creamy Malai Paneer — zero tofu/sponge/processed-cheese sheen, zero branding/text, zero shared crops.*
- **01 (`fresh-paneer-01.webp`) — Main Ceramic Plate on Light Grey:** *Commercial DSLR studio food photograph of uniform freshly diced milky-white Indian Fresh Paneer cubes stacked cleanly on a simple round white ceramic plate over a minimal pale light-grey studio surface (`#ECEEEF`), authentic slightly moist porous curd texture with crisp knife edges, soft natural studio lighting and delicate grounded shadows, 85mm f/2.8 lens, 1:1 square.*
- **02 (`fresh-paneer-02.webp`) — Whole Rectangular Block on Wooden Board:** *Side-three-quarter studio shot of a whole fresh rectangular block of milky-white Indian Fresh Paneer resting solidly on a natural mango-wood chopping board in diffused daylight, crisp pressed edges with subtle muslin texture imprint, shallow background depth.*
- **03 (`fresh-paneer-03.webp`) — Extreme Macro Texture:** *Extreme 100mm DSLR macro close-up filling the frame with freshly cut milky-white Indian Fresh Paneer showing fine natural moisture curds, subtle tiny air pores, and clean slightly grainy natural cottage cheese break-edges — zero artificial cream glaze, zero plastic shine.*
- **04 (`fresh-paneer-04.webp`) — Freshly Sliced Slabs on Dark Stone:** *Clean 45-degree studio photograph of 4–5 thick rectangular freshly sliced slabs of Fresh Paneer fanned neatly on a textured dark charcoal stone platter with soft directional side lighting catching realistic moist curd ridges.*
- **05 (`fresh-paneer-05.webp`) — Traditional Indian Stainless Steel Plate:** *Authentic Indian kitchen presentation showing freshly cut Fresh Paneer cubes arranged naturally on a gleaming traditional Indian stainless steel thali/plate resting on a warm kitchen countertop in soft morning light.*
- **06 (`fresh-paneer-06.webp`) — Cutting Action with Kitchen Knife:** *Dynamic food photography capturing a hand holding a sharp stainless kitchen knife slicing cleanly down through a fresh milky-white paneer block on a dark timber cutting board alongside newly parted uniform paneer cubes, realistic curd crumb edge.*
- **07 (`fresh-paneer-07.webp`) — Overhead Natural Daylight Ceramics:** *Crisp 90-degree flat-lay overhead photography of naturally arranged milky-white Fresh Paneer cubes on a matte round stoneware plate set over light woven cotton cloth under even soft natural window daylight.*
- **08 (`fresh-paneer-08.webp`) — Cooking Preparation Mise-en-Place:** *Clean, appetizing Indian home kitchen cooking preparation scene showing a bowl/board of raw fresh paneer cubes alongside whole ripe red tomatoes, crisp green capsicum slices, red onions, and fresh green coriander sprigs ready for cooking — raw state clearly distinguishable.*
- **09 (`fresh-paneer-09.webp`) — Serving Suggestion (Paneer Bhurji):** *Warm, rustic culinary serving suggestion photograph (distinct from raw cubes): freshly sautéed golden-spiced Indian paneer bhurji crumbled soft white paneer cooked gently with onions, tomatoes, green peas glaze, and chopped cilantro served steaming hot inside a traditional dark stoneware/brass katori bowl.*
- **10 (`fresh-paneer-10.webp`) — Natural Dairy Muslin Presentation:** *Calm early-morning Indian dairy lifestyle photograph showing a fresh milky-white rectangular paneer block resting gently atop clean folded white cotton muslin cloth on oak wood bathed in soft natural side window sunlight.*

#### `malai-paneer` (Malai Paneer · 500 g — **10 Independent DSLR Studio Shots Blocked by HTTP 429 Quota Reset**)
> *Current gallery retains white-balanced reference renders from `raw_malai_paneer.jpg`. All 10 bespoke DSLR shots below enforce milky-white/ivory authentic Indian Malai Paneer texture with tiny natural pores, moist curds, soft crumbly cutting edges — never firm tofu, cheddar, plastic sheen, or recycled crops.*
- **Shot 01 (Main Ceramic Cream Studio):** *Commercial DSLR food photograph of uniformly cut soft milky-white/ivory Indian Malai Paneer cubes stacked neatly on a handcrafted speckled matte ceramic plate over a clean soft cream studio backdrop (`#F6F1E7`), delicate natural cheese pores, moist curds, soft directional side daylight.*
- **Shot 02 (Fresh Paneer Block on Wood):** *Thick artisanal rectangular block of snow-white moist Malai Paneer with two cleanly sliced thick slabs leaning against its cut face on a warm seasoned teak chopping board, soft kitchen window daylight, shallow depth of field.*
- **Shot 03 (Macro Creamy Pore Texture):** *Extreme 100mm macro food photograph filling the frame with the exposed freshly sliced interior of soft Malai Paneer showing fine moist milk curds, natural tiny pin-hole pores, slightly uneven artisan cut edges, crisp texture, zero plastic shine.*
- **Shot 04 (Traditional Brass Plate Indian Kitchen):** *Fresh milky-white Malai Paneer cubes served neatly in a traditional clean hammered Indian brass thali/plate with a soft rustic Indian home kitchen counter subtly blurred in background light.*
- **Shot 05 (Dark Slate Studio Lighting):** *Dramatic minimalist studio photograph of fresh Malai Paneer cubes arranged artistically on a matte charcoal slate plate with sculpted softbox side lighting emphasizing milky ivory edges against dark charcoal background.*
- **Shot 06 (Freshly Cut Interior with Kitchen Knife):** *Dynamic 45-degree DSLR shot capturing a sharp brushed-steel Indian kitchen chef knife cleanly slicing through a tall fresh Malai Paneer block on parchment/wood, revealing the ultra-soft moist interior mid-cut.*
- **Shot 07 (Overhead Top View on White Ceramic):** *Crisp 90-degree flat-lay overhead photography of naturally scattered fresh milky-white Malai Paneer cubes arranged organically on a round matte white stoneware plate over light neutral linen.*
- **Shot 08 (Cooking Lifestyle Prep):** *Bright airy culinary prep scene showing fresh Malai Paneer cubes on a cutting board alongside ripe red tomatoes, crisp green capsicum, fresh green coriander sprigs, ginger, and unbranded whole spices in ceramic bowls.*
- **Shot 09 (Serving Suggestion — Malai Paneer Tikka):** *Appetizing gourmet serving suggestion (distinct from raw paneer): tender skewered Malai Paneer tikka pieces with delicate golden tandoor char marks garnished with light coriander and lemon wedge on a warm stoneware platter.*
- **Shot 10 (Traditional Muslin Morning Light):** *Artisanal fresh Malai Paneer block resting gently atop clean folded white cotton muslin cloth near an airy Indian dairy table bathed in soft warm golden morning sunlight casting natural shadows.*

#### `full-cream-milk` (Full Cream Milk · 1 litre · **Reference: `product-milk.jpg`**)
- **Shot 01 (Primary White):** *Pure `#FFFFFF` studio commercial photograph of a clear glass dairy carafe filled with rich creamy white Full Cream Milk beside a short clear crystal tumbler brim-full of milk, natural studio rim highlights and soft grey glass contact shadow.*
- **Shot 02 (Lifestyle):** *Chilled clear glass bottle and drinking glass of rich full cream milk on a sunlit marble kitchen counter beside a clean stainless steel saucer, morning breakfast light.*
- **Shot 03 (Macro Texture):** *Macro close-up at liquid surface level inside a crystal tumbler showing thick velvety full-cream milk crown and clean glass meniscus.*
- **Shot 04 (45° Angle):** *45-degree three-quarter studio angle of glass milk carafe mid-pour into a crystal glass over clean pale stone studio backdrop, natural motion freeze.*
- **Shot 05 (Usage):** *Pouring chilled full cream milk into a morning ceramic bowl or making traditional malai/tea on a bright kitchen table, realistic domestic lighting.*

#### `toned-milk` (Toned Milk · 1 litre · **Reference: `product-toned-milk.jpg`**)
- **Shot 01 (Primary White):** *Pure `#FFFFFF` studio commercial photograph of a tall slender highball crystal glass filled smoothly with fresh light Toned Milk, delicate glass highlights and clean ground shadow.*
- **Shot 02 (Lifestyle):** *Two tall glasses of cool refreshing toned milk beside light breakfast toast and fruit on a bright minimalist oak breakfast table, crisp daylight.*
- **Shot 03 (Macro Texture):** *Close-up upper glass studio shot capturing crystal-clear glass rim and silky light-bodied milk sheen.*
- **Shot 04 (45° Angle):** *Slightly elevated 45-degree studio shot of tall toned milk glass alongside an unlabelled clear glass milk carafe on cool off-white slate surface.*
- **Shot 05 (Usage):** *Pouring fresh toned milk smoothly into a morning glass tumbler from a chilled pitcher in a bright contemporary Indian kitchen.*

#### `cow-milk` (Cow Milk · 500 ml · **References: `raw_cow_milk.jpg`, `raw_milk_001.jpg`**)
- **Shot 01 (Primary White):** *Pure `#FFFFFF` studio commercial photograph of a classic 500ml clear glass bottle and small glass tumbler filled with natural A2 desi cow milk (subtle warm golden-ivory cream undertone compared to buffalo milk), clean contact shadow.*
- **Shot 02 (Lifestyle):** *Traditional Indian morning lifestyle shot: clear glass and small polished brass tumbler of fresh desi cow milk on a sunlit veranda stone table with morning greens blurred in distance.*
- **Shot 03 (Macro Texture):** *Macro close-up of gentle milk froth bubbles and warm ivory hue at the rim of a crystal milk glass.*
- **Shot 04 (45° Angle):** *45-degree side studio view of an unlabelled crystal bottle and half-filled tasting glass on light warm limestone background.*
- **Shot 05 (Usage):** *Pouring warm fresh cow milk cleanly from a small stainless saucepan into a child's glass tumbler, warm morning home light.*
