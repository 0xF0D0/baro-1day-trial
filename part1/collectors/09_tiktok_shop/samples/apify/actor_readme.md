# TikTok Shop Scraper

Find what's selling on TikTok Shop before your competitors do. Search by keyword or seller, get rich product data (sold counts, ratings, prices, sellers, variants), and rank by whatever signal matters to you.

_A DIY Kalodata alternative for winning products discovery, competitor analytics and dropshipping research._

## 🛍️ What it does

Most TikTok Shop scrapers expect you to already know the product URL. But TikTok Shop value is the products you don't know about yet, the ones that go from 0 to 50,000 units in a week.

This scraper is built around discovery:

- **Keyword catalog search**: feed it `vitamin c serum` and it returns the top products for that term, ranked by relevance, sales, newest, or price. Like Amazon Best Sellers but for TikTok.
- **Sold counts and creator counts**: rank discovered products by actual sales velocity or by how many creators are pushing them. That's the signal for what's about to go viral.
- **Bulk processing**: screen thousands of products in one run. Pair with Apify Schedules for daily winner-spotting feeds.

Built for dropshippers spotting winning products, analysts running competitor spy, and brand owners tracking sales & GMV over time.

## 💎 Add-ons

Optional fields, all off by default. Turn on only what a run needs.

- **Creator count** *(paid)*: How many TikTok creators are promoting the product in videos, plus their video links. A high or rising creator count is the earliest public sign a product is being pushed hard and about to trend.
- **First-seen date** *(free)*: An estimate of when the product first went live, so you can tell a fresh opportunity from a saturated one.
- **Extra reviews** *(paid per extra review)*: Up to 600 reviews per product, beyond the 5 bundled free, for sentiment analysis and catching product issues before you commit inventory. Tune via **Reviews sort order** (newest, or TikTok's recommended ranking) and **Reviews star filter** (return only 1-star reviews for quality screening, or any specific rating 1–5).

## 📋 How to use it

### Step 1: Pick your inputs
Mix and match any of the following:
- **Product URLs**: any TikTok Shop product link, including short links (`vm.tiktok.com/...`)
- **Shop URLs**: `tiktok.com/shop/s/SHOP_ID` or `tiktok.com/shop/store/SLUG/SHOP_ID` (the URL must contain the numeric shop ID; `@username/shop` links are not supported)
- **Product IDs**: the 18 to 19 digit numeric IDs
- **Shop IDs**: the numeric ID of a shop
- **Keywords**: catalog search terms like `vitamin c serum`
- **Hashtags**: TikTok hashtag names like `cleantok` or `tiktokmademebuyit`, with or without the `#`. Returns products tagged in shoppable videos under that hashtag.
- **Categories**: pick from the dropdown to scrape a full TikTok Shop category (Beauty & Personal Care, Womenswear, Electronics, etc.) in its native browse order. Each category adds ~15–30 seconds for a one-time captcha solve.
- **Category URLs** *(advanced)*: paste full `shop.tiktok.com/us/c/<slug>/<id>` URLs or numeric category IDs for subcategories not in the dropdown.

US, UK, Mexico and Thailand storefronts are live today. More regions are on the roadmap — [vote for the market we add next.](https://strawpoll.com/PbZqb8AeByN)

### Step 2: Tune the run
- **Max products per source**: cap how many products to fetch per shop or keyword (URLs and IDs always return one)
- **Sort by**: Relevance, Best selling, Newest, Price low to high, or Price high to low
- **Add-ons**: turn on 'Include more than 5 reviews', Creator count, or First-seen date if you want them. All off by default. Up to 5 reviews per product are always included for free.
- **Output toggles**: switch off any field you don't need so rows stay lean

### Step 3: Read your results
Click Start. Each row in the Output tab is one product. Always check the `status` field first. `Success` means the row is good. Anything else explains what happened (geo-block, region restriction, delisted product) and is not billed.

### Example output

A complete row, with the Creator count, First-seen date, and Extra reviews
add-ons all enabled. The `videoCount`, `creatorCount`, `promoterVideoUrls`,
`firstSeen`, and `reviews` fields appear only when their add-on is turned on.

```json
{
    "status": "Success",
    "productId": "1731349100249977343",
    "source": "url",
    "inputUrl": "https://www.tiktok.com/shop/pdp/1731349100249977343",
    "productUrl": "https://www.tiktok.com/shop/pdp/perfectamino-powder-essential-aminos-for-muscle-collagen/1731349100249977343",
    "title": "BODYHEALTH Perfect Amino Powder - Essential Amino Acids for Muscle Recovery",
    "description": "Build protein, muscle and collagen without the caloric impact of a full meal.",
    "currentPrice": 32.95,
    "priceDisplay": "$32.95",
    "originalPrice": 45.95,
    "discountPercent": 28,
    "currency": "USD",
    "rating": 4.8,
    "reviewCount": 8807,
    "soldCount": 10347,
    "sellerId": "7495492798404069887",
    "sellerName": "BODYHEALTH",
    "sellerFollowers": 8600,
    "sellerRating": 4.2,
    "sellerSold": 30100,
    "sellerResponseRatePct": 66,
    "sellerShipsWithinDays": 2,
    "sellerPositiveFeedbackPct": 79,
    "sellerProductCount": 24,
    "sellerReviewCount": 3120,
    "sellerVideoCount": 410,
    "sellerUrl": "https://www.tiktok.com/shop/store/bodyhealth/7495492798404069887",
    "sellerIsOfficial": true,
    "businessName": "BodyHealth LLC",
    "brand": "BODYHEALTH",
    "categoryPath": "Health > Nutrition & Wellness > Fitness Supplements > Protein Supplements",
    "videoCount": 312,
    "creatorCount": 214,
    "promoterVideoUrls": [
        "https://www.tiktok.com/@fitwithjen/video/7401234567890123456",
        "https://www.tiktok.com/@gymrattips/video/7402345678901234567"
    ],
    "firstSeen": "2024-11-03T08:12:40.000Z",
    "imageUrls": [
        "https://p16-oec-general-useast5.ttcdn-us.com/tos-useast5-i-omjb5zjo8w-tx/5dc8403f93fc457183c1f001c4adc60a~tplv-fhlh96nyum-crop-webp:1600:1600.webp"
    ],
    "shippingOrigin": "745 Main St, Dunedin, Florida, 34698, United States",
    "variants": [
        { "skuId": "1731349107483185663", "price": 32.95, "currency": "USD", "properties": "Flavor: Unflavored", "available": 1240 },
        { "skuId": "1731349107483251199", "price": 34.95, "currency": "USD", "properties": "Flavor: Mixed Berry", "available": 86 }
    ],
    "variantOptions": ["Flavor"],
    "reviews": [
        {
            "reviewId": "7405512340987654321",
            "rating": 5,
            "timestamp": "2026-04-22T17:31:09.000Z",
            "user": "Marcus T.",
            "userId": "7298471230984712309",
            "userAvatar": "https://p16-oec-general-useast5.ttcdn-us.com/.../avatar.webp",
            "verified": true,
            "incentivized": false,
            "content": "Mixes clean, no aftertaste. Down 6 lbs and keeping muscle.",
            "skuId": "1731349107483185663",
            "images": ["https://p16-oec-general-useast5.ttcdn-us.com/.../review-photo.webp"],
            "source": "api"
        },
        {
            "reviewId": "7404998877665544332",
            "rating": 4,
            "timestamp": "2026-04-18T09:05:44.000Z",
            "user": "Dana R.",
            "userId": "7301122334455667788",
            "userAvatar": "https://p16-oec-general-useast5.ttcdn-us.com/.../avatar.webp",
            "verified": true,
            "incentivized": false,
            "content": "Good value. Wish the berry flavor was a little less sweet.",
            "skuId": "1731349107483251199",
            "images": null,
            "source": "api"
        }
    ],
    "scrapeTimestamp": "2026-05-17T14:22:11.000Z",
    "error": null
}
```

## 💰 Pricing

Pay only for products successfully delivered. No subscription, no minimum.

| Event | Price | When |
|---|---|---|
| Product scraped | **$1.99 per 1,000 products** | per product successfully returned. Always includes up to 5 reviews for free. |
| Hashtag product | **$5 per 1,000 products** | per product discovered via a hashtag input. |
| Review extras | **$2 per 1,000 reviews** | each review past the 5th, only when 'Include more than 5 reviews' is enabled. |
| Creator count | **$20 per 1,000 products** | only when the count was successfully resolved. |

No charge for failed rows, geo-blocked rows, or rows where the seller has delisted the product.

### Examples
- 1,000 products, no add-ons: **$1.99**
- 1,000 products, 25 reviews each: $1.99 + (20,000 × $0.002) = **$41.99**
- 1,000 products with creator count: $1.99 + $20.00 = **$21.99**

## 💡 Good to know

- **US, UK, Mexico and Thailand storefronts are live today.** France, Japan, Indonesia, Malaysia, Vietnam, Singapore, and the Philippines are on the roadmap. [Vote for which region we add next.](https://strawpoll.com/PbZqb8AeByN)
- **Auto-deduplication**: the same product surfacing through a URL and a keyword is only billed once.
- **Geo-blocked rows** ("Product not available in this country or region") are detected and not billed.
- **Reviews come sorted newest-first.** Up to 5 are bundled in the base charge.
- **Output toggles** let you trim each row to just the fields you actually need.
- Files and datasets are stored in your Apify storage. How long they're kept depends on your Apify plan.

## ❓ FAQ

**Why did some products fail?**
Most failures are because the seller delisted the product, the listing is region-restricted, or the IP got temporarily flagged. Check the `status` field on each row, it explains exactly what happened. None of these cases are billed.

**Why is the price different from what I see on TikTok Shop?**
TikTok shows different promotional discounts to anonymous visitors than to logged-in users; anonymous visitors get a larger discount on the same SKU. The Actor reports prices as a logged-out shopper sees them at scrape time. In our tests, anonymous `currentPrice` runs roughly 5-15% below the logged-in promo price for the same SKU. The `originalPrice` field is the seller's list price (struck-through MSRP) and is identical for both viewer types; use it if you need a stable catalog reference. Prices reflect a single scrape moment; TikTok rotates promotional discounts continuously, so a re-run minutes later may report slightly different `currentPrice` values for the same SKU.

**Which proxy should I use?**
Nothing on your side. Networking is managed by the Actor automatically. It's tuned to keep success rates high and runs cheap.

**Can I scrape outside the US?**
The **UK, Mexico and Thailand** storefronts work today too — pick one in the Regional dropdown. Other regions (FR, JP, ID, MY, VN, SG, PH) are on the roadmap. [Vote for which region we add next.](https://strawpoll.com/PbZqb8AeByN)

**Can I run this on a schedule?**
Yes. Use Apify Schedules to run the Actor on any cadence (hourly, daily, custom cron).

**How long are my results stored?**
Results live in your Apify dataset. How long they're kept depends on your Apify plan.

## 🔗 Other tools you might like

- [TikTok Video Downloader](https://apify.com/lurkapi/tiktok-video-downloader) - Download TikTok videos without watermark in bulk.

## ⚖️ Legal Disclaimer

This Actor is for educational, research, and market-intelligence use. It extracts public commercial data (product titles, prices, ratings, seller info, and review counts) from publicly accessible TikTok Shop pages. The developer does not host, store, or possess any output; all data is delivered to your Apify dataset. Customer review records, when included, contain only the publicly displayed reviewer handle; no email or contact information is collected.

By running this Actor, **you assume full responsibility** for compliance with applicable laws, TikTok's Terms of Service, and any data-protection regulations in your target jurisdiction (e.g. GDPR, CCPA). The developer assumes **no liability** for platform blocks, bans, regulatory actions, or any other consequences of your use.

This software is provided **"as-is"** with no warranty. Sales counts, ratings, and other TikTok-exposed metrics are public approximations, not audited figures. Data availability depends on TikTok at run time.

**Keywords:** TikTok Shop scraper, TikTok Shop API, TikTok Shop spy, TikTok Shop analytics, TikTok Shop sales tracker, Kalodata alternative, GMV tracker, product spy, competitor spy, creator ads, sponsored content, winning products, hot products, best-selling products, TikTok dropshipping tool, TikTok product research, ecommerce scraper, product data, sales data, TikTok products, dropshipping research, TikTok Shop crawler

