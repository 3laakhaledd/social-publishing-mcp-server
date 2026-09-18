# Social Publishing MCP Server

MCP server for **organic social publishing** to Facebook, Instagram & TikTok. Deploy on Railway, connect to ClickUp Brain via MCP Connect, and publish posts directly from chat.

## Tools (15 total)

### Facebook Page (6 tools)
| Tool | Description |
|------|-------------|
| `fb_publish_text_post` | Text-only post |
| `fb_publish_photo_post` | Single photo post |
| `fb_publish_multi_photo_post` | Multi-photo album (2-10) |
| `fb_publish_link_post` | Link share with preview |
| `fb_publish_video_post` | Video / Reel |
| `fb_schedule_post` | Schedule a post (10min - 75 days) |

### Instagram (4 tools)
| Tool | Description |
|------|-------------|
| `ig_publish_photo` | Single photo post |
| `ig_publish_carousel` | Carousel (2-10 images) |
| `ig_publish_reel` | Reel with async processing |
| `ig_publish_story` | Story (image or video) |

### TikTok (5 tools)
| Tool | Description |
|------|-------------|
| `tiktok_query_creator_info` | Get privacy options before posting |
| `tiktok_publish_video` | Direct post video |
| `tiktok_publish_photos` | Direct post photo carousel |
| `tiktok_upload_to_inbox` | Send video to creator's inbox (draft) |
| `tiktok_check_publish_status` | Poll publish status |

## Prerequisites

### Meta (Facebook + Instagram)
1. Create a Meta App at [developers.facebook.com](https://developers.facebook.com)
2. Add **Facebook Login** and **Instagram Basic Display** products
3. Generate a **Page Access Token** with these permissions:
   - `pages_manage_posts`
   - `pages_read_engagement`
   - `instagram_basic`
   - `instagram_content_publish`
4. Get your Facebook Page ID and Instagram Business Account ID

### TikTok
1. Register an app at [developers.tiktok.com](https://developers.tiktok.com)
2. Add the **Content Posting API** product
3. Request `video.publish` and `video.upload` scopes
4. Verify your domain in the TikTok developer portal
5. **Important**: Until your app passes TikTok's audit, posts are private-only

## Deploy to Railway

1. Fork this repo
2. Create a new project on [Railway](https://railway.app)
3. Connect your GitHub repo
4. Add environment variables from `.env.example`
5. Deploy - Railway will build from the Dockerfile

## Connect to ClickUp Brain

1. Go to ClickUp Settings > Integrations > MCP Connect
2. Add a new MCP server
3. Enter your Railway deployment URL + `/sse` as the SSE endpoint
4. The 15 tools will appear in ClickUp Brain

## Local Development

```bash
pip install -r requirements.txt
cp .env.example .env
# Fill in your credentials in .env
python server.py
```

Server runs on `http://localhost:8000`. Health check at `/`, SSE at `/sse`.

## Architecture

- **Python 3.12** + FastMCP + Starlette
- **SSE transport** for MCP protocol
- **httpx** async HTTP client for all API calls
- Same stack as [whatsapp-mcp-server](https://github.com/3laakhaledd/whatsapp-mcp-server)
