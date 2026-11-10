from . import (amazon, brand_site_and_emails, google_ads_transparency, google_results, meta_ad_library,
               retail_shelf, search_interest, tiktok_ads, tiktok_posts, tiktok_shop)

MAPPERS = {m.SOURCE: m for m in (amazon, brand_site_and_emails, google_ads_transparency, google_results,
                                 meta_ad_library, retail_shelf, search_interest, tiktok_ads, tiktok_posts,
                                 tiktok_shop)}
