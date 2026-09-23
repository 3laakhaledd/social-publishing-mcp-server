#!/usr/bin/env python3
"""
Social Publishing MCP Server
Publish organic content to Facebook, Instagram & TikTok.
Read Facebook & Instagram conversations/inbox.
Connects to ClickUp Brain via MCP Connect.
"""

import os, json, logging, asyncio, httpx, uvicorn
from typing import Any
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount

# Config
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")
META_API_BASE = f"https://graph.facebook.com/{META_API_VERSION}"
META_PAGE_ACCESS_TOKEN = os.getenv("META_PAGE_ACCESS_TOKEN", "")
META_PAGE_ID = os.getenv("META_PAGE_ID", "")
META_IG_USER_ID = os.getenv("META_IG_USER_ID", "")
TIKTOK_ACCESS_TOKEN = os.getenv("TIKTOK_ACCESS_TOKEN", "")
TIKTOK_API_BASE = "https://open.tiktokapis.com/v2"
PORT = int(os.getenv("PORT", "8000"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("social-publish-mcp")
mcp = FastMCP("Social Publishing MCP Server")


# Helpers
async def _meta_post(endpoint, payload=None, data=None):
    url = f"{META_API_BASE}/{endpoint}"
    async with httpx.AsyncClient(timeout=60) as c:
        if data:
            r = await c.post(url, headers={"Authorization": f"Bearer {META_PAGE_ACCESS_TOKEN}"}, data=data)
        else:
            r = await c.post(url, headers={"Authorization": f"Bearer {META_PAGE_ACCESS_TOKEN}", "Content-Type": "application/json"}, json=payload or {})
        r.raise_for_status()
        return r.json()


async def _meta_get(endpoint, params=None):
    url = f"{META_API_BASE}/{endpoint}"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.get(url, headers={"Authorization": f"Bearer {META_PAGE_ACCESS_TOKEN}"}, params=params)
        r.raise_for_status()
        return r.json()


async def _tiktok_post(path, payload):
    url = f"{TIKTOK_API_BASE}/{path}"
    async with httpx.AsyncClient(timeout=60) as c:
        r = await c.post(url, headers={"Authorization": f"Bearer {TIKTOK_ACCESS_TOKEN}", "Content-Type": "application/json; charset=UTF-8"}, json=payload)
        r.raise_for_status()
        return r.json()


# == FACEBOOK PAGE ==

@mcp.tool()
async def fb_publish_text_post(message: str) -> str:
    """
    Publish a text-only post to the Facebook Page.

    Args:
        message: The post text (supports hashtags, mentions, links)
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    result = await _meta_post(f"{META_PAGE_ID}/feed", payload={"message": message})
    return json.dumps({"status": "published", "post_id": result.get("id")}, indent=2)


@mcp.tool()
async def fb_publish_photo_post(photo_url: str, caption: str = "") -> str:
    """
    Publish a photo post to the Facebook Page.

    Args:
        photo_url: Public URL of the image
        caption: Optional caption / message for the post
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    payload: dict[str, Any] = {"url": photo_url, "published": True}
    if caption:
        payload["message"] = caption
    result = await _meta_post(f"{META_PAGE_ID}/photos", payload=payload)
    return json.dumps({"status": "published", "photo_id": result.get("id"), "post_id": result.get("post_id")}, indent=2)


@mcp.tool()
async def fb_publish_multi_photo_post(photo_urls: list[str], caption: str = "") -> str:
    """
    Publish a multi-photo post (2-10 photos) to the Facebook Page.

    Args:
        photo_urls: List of public image URLs (2-10)
        caption: Caption for the combined post
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    if len(photo_urls) < 2:
        return json.dumps({"error": "Need at least 2 photos"})
    photo_ids = []
    for url in photo_urls:
        r = await _meta_post(f"{META_PAGE_ID}/photos", payload={"url": url, "published": False})
        photo_ids.append(r["id"])
    data: dict[str, Any] = {}
    if caption:
        data["message"] = caption
    for i, pid in enumerate(photo_ids):
        data[f"attached_media[{i}]"] = json.dumps({"media_fbid": pid})
    result = await _meta_post(f"{META_PAGE_ID}/feed", data=data)
    return json.dumps({"status": "published", "post_id": result.get("id"), "photo_count": len(photo_ids)}, indent=2)


@mcp.tool()
async def fb_publish_link_post(link: str, message: str = "") -> str:
    """
    Publish a link-share post to the Facebook Page (renders link preview).

    Args:
        link: The URL to share
        message: Optional text above the link preview
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    payload: dict[str, Any] = {"link": link}
    if message:
        payload["message"] = message
    result = await _meta_post(f"{META_PAGE_ID}/feed", payload=payload)
    return json.dumps({"status": "published", "post_id": result.get("id")}, indent=2)


@mcp.tool()
async def fb_publish_video_post(video_url: str, title: str = "", description: str = "") -> str:
    """
    Publish a video to the Facebook Page.

    Args:
        video_url: Public URL of the video file (MP4 recommended)
        title: Optional video title
        description: Optional video description / caption
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    payload: dict[str, Any] = {"file_url": video_url, "published": True}
    if title:
        payload["title"] = title
    if description:
        payload["description"] = description
    result = await _meta_post(f"{META_PAGE_ID}/videos", payload=payload)
    return json.dumps({"status": "published", "video_id": result.get("id")}, indent=2)


@mcp.tool()
async def fb_schedule_post(message: str, scheduled_publish_time: int, photo_url: str = "", link: str = "") -> str:
    """
    Schedule a post for future publishing on the Facebook Page.

    Args:
        message: The post text
        scheduled_publish_time: Unix timestamp (must be 10min to 75 days in the future)
        photo_url: Optional photo URL to attach
        link: Optional link to share
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    if photo_url:
        payload: dict[str, Any] = {"url": photo_url, "message": message, "published": False, "scheduled_publish_time": scheduled_publish_time}
        result = await _meta_post(f"{META_PAGE_ID}/photos", payload=payload)
    else:
        payload = {"message": message, "published": False, "scheduled_publish_time": scheduled_publish_time}
        if link:
            payload["link"] = link
        result = await _meta_post(f"{META_PAGE_ID}/feed", payload=payload)
    return json.dumps({"status": "scheduled", "post_id": result.get("id"), "scheduled_for": scheduled_publish_time}, indent=2)


# == FACEBOOK CONVERSATIONS / INBOX ==

@mcp.tool()
async def fb_list_conversations(limit: int = 25, after: str = "") -> str:
    """
    List recent Facebook Page conversations (Messenger inbox).
    Returns participant names, message count, and last update time.

    Args:
        limit: Number of conversations to return (max 100, default 25)
        after: Pagination cursor from a previous response to get the next page
    """
    if not META_PAGE_ID:
        return json.dumps({"error": "META_PAGE_ID not configured"})
    params = {
        "fields": "participants,updated_time,message_count,id",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after
    result = await _meta_get(f"{META_PAGE_ID}/conversations", params=params)
    conversations = result.get("data", [])
    next_cursor = result.get("paging", {}).get("cursors", {}).get("after", "")
    has_more = bool(result.get("paging", {}).get("next"))
    output = []
    for conv in conversations:
        participants = [
            {"name": p.get("name", ""), "id": p.get("id", "")}
            for p in conv.get("participants", {}).get("data", [])
        ]
        output.append({
            "conversation_id": conv.get("id"),
            "participants": participants,
            "message_count": conv.get("message_count"),
            "updated_time": conv.get("updated_time"),
        })
    return json.dumps({
        "conversations": output,
        "count": len(output),
        "has_more": has_more,
        "next_cursor": next_cursor if has_more else None,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def fb_get_conversation_messages(conversation_id: str, limit: int = 10, after: str = "") -> str:
    """
    Get messages from a specific Facebook Page conversation.

    Args:
        conversation_id: The conversation ID from fb_list_conversations
        limit: Number of messages to return (max 100, default 10)
        after: Pagination cursor for next page
    """
    params = {
        "fields": "message,from,created_time,attachments",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after
    result = await _meta_get(f"{conversation_id}/messages", params=params)
    messages = result.get("data", [])
    next_cursor = result.get("paging", {}).get("cursors", {}).get("after", "")
    has_more = bool(result.get("paging", {}).get("next"))
    output = []
    for msg in messages:
        output.append({
            "id": msg.get("id"),
            "from": msg.get("from", {}),
            "message": msg.get("message", ""),
            "created_time": msg.get("created_time"),
        })
    return json.dumps({
        "messages": output,
        "count": len(output),
        "has_more": has_more,
        "next_cursor": next_cursor if has_more else None,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def fb_get_participant_profile(user_id: str) -> str:
    """
    Get a Facebook user profile from a Page conversation (name, profile pic).
    Only works for users who have messaged the Page.

    Args:
        user_id: The participant user ID from fb_list_conversations or fb_get_conversation_messages
    """
    params = {
        "fields": "name,first_name,last_name,profile_pic",
    }
    result = await _meta_get(user_id, params=params)
    return json.dumps(result, indent=2, ensure_ascii=False)


# == INSTAGRAM (Content Publishing API) ==

@mcp.tool()
async def ig_publish_photo(image_url: str, caption: str = "") -> str:
    """
    Publish a single photo to Instagram.

    Args:
        image_url: Public URL of the image (JPEG recommended, max 8MB)
        caption: Caption text (supports hashtags and @mentions)
    """
    if not META_IG_USER_ID:
        return json.dumps({"error": "META_IG_USER_ID not configured"})
    cp: dict[str, Any] = {"image_url": image_url}
    if caption:
        cp["caption"] = caption
    container = await _meta_post(f"{META_IG_USER_ID}/media", payload=cp)
    result = await _meta_post(f"{META_IG_USER_ID}/media_publish", payload={"creation_id": container["id"]})
    return json.dumps({"status": "published", "ig_media_id": result.get("id")}, indent=2)


@mcp.tool()
async def ig_publish_carousel(image_urls: list[str], caption: str = "") -> str:
    """
    Publish a carousel (multi-image) post to Instagram.

    Args:
        image_urls: List of public image URLs (2-10 images)
        caption: Caption for the carousel post
    """
    if not META_IG_USER_ID:
        return json.dumps({"error": "META_IG_USER_ID not configured"})
    if len(image_urls) < 2:
        return json.dumps({"error": "Carousel needs at least 2 images"})
    child_ids = []
    for url in image_urls:
        child = await _meta_post(f"{META_IG_USER_ID}/media", payload={"image_url": url, "is_carousel_item": True})
        child_ids.append(child["id"])
    cp: dict[str, Any] = {"media_type": "CAROUSEL", "children": ",".join(child_ids)}
    if caption:
        cp["caption"] = caption
    container = await _meta_post(f"{META_IG_USER_ID}/media", payload=cp)
    result = await _meta_post(f"{META_IG_USER_ID}/media_publish", payload={"creation_id": container["id"]})
    return json.dumps({"status": "published", "ig_media_id": result.get("id"), "image_count": len(child_ids)}, indent=2)


@mcp.tool()
async def ig_publish_reel(video_url: str, caption: str = "", cover_url: str = "", share_to_feed: bool = True) -> str:
    """
    Publish a Reel to Instagram.

    Args:
        video_url: Public URL of the video (MP4, 3s-15min, max 1GB)
        caption: Caption text
        cover_url: Optional cover image URL
        share_to_feed: Also share to the main feed (default True)
    """
    if not META_IG_USER_ID:
        return json.dumps({"error": "META_IG_USER_ID not configured"})
    p: dict[str, Any] = {"media_type": "REELS", "video_url": video_url, "share_to_feed": share_to_feed}
    if caption:
        p["caption"] = caption
    if cover_url:
        p["cover_url"] = cover_url
    container = await _meta_post(f"{META_IG_USER_ID}/media", payload=p)
    cid = container["id"]
    for _ in range(30):
        s = await _meta_get(cid, params={"fields": "status_code"})
        if s.get("status_code") == "FINISHED":
            break
        if s.get("status_code") == "ERROR":
            return json.dumps({"error": "Video processing failed", "details": s})
        await asyncio.sleep(5)
    result = await _meta_post(f"{META_IG_USER_ID}/media_publish", payload={"creation_id": cid})
    return json.dumps({"status": "published", "ig_media_id": result.get("id")}, indent=2)


@mcp.tool()
async def ig_publish_story(image_url: str = "", video_url: str = "") -> str:
    """
    Publish a Story to Instagram (image or video).

    Args:
        image_url: Public URL of the image (provide either image_url or video_url)
        video_url: Public URL of the video (provide either image_url or video_url)
    """
    if not META_IG_USER_ID:
        return json.dumps({"error": "META_IG_USER_ID not configured"})
    if not image_url and not video_url:
        return json.dumps({"error": "Provide either image_url or video_url"})
    p: dict[str, Any] = {"media_type": "STORIES"}
    if image_url:
        p["image_url"] = image_url
    else:
        p["video_url"] = video_url
    container = await _meta_post(f"{META_IG_USER_ID}/media", payload=p)
    cid = container["id"]
    if video_url:
        for _ in range(30):
            s = await _meta_get(cid, params={"fields": "status_code"})
            if s.get("status_code") == "FINISHED":
                break
            if s.get("status_code") == "ERROR":
                return json.dumps({"error": "Story processing failed"})
            await asyncio.sleep(5)
    result = await _meta_post(f"{META_IG_USER_ID}/media_publish", payload={"creation_id": cid})
    return json.dumps({"status": "published", "ig_media_id": result.get("id")}, indent=2)


# == INSTAGRAM CONVERSATIONS / INBOX ==

@mcp.tool()
async def ig_list_conversations(limit: int = 25, after: str = "") -> str:
    """
    List recent Instagram Direct conversations.
    Returns participant usernames and last update time.

    Args:
        limit: Number of conversations to return (max 100, default 25)
        after: Pagination cursor from a previous response to get the next page
    """
    if not META_IG_USER_ID:
        return json.dumps({"error": "META_IG_USER_ID not configured"})
    params = {
        "fields": "participants,updated_time,id",
        "platform": "instagram",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after
    result = await _meta_get(f"{META_IG_USER_ID}/conversations", params=params)
    conversations = result.get("data", [])
    next_cursor = result.get("paging", {}).get("cursors", {}).get("after", "")
    has_more = bool(result.get("paging", {}).get("next"))
    output = []
    for conv in conversations:
        participants = [
            {"name": p.get("name", ""), "username": p.get("username", ""), "id": p.get("id", "")}
            for p in conv.get("participants", {}).get("data", [])
        ]
        output.append({
            "conversation_id": conv.get("id"),
            "participants": participants,
            "updated_time": conv.get("updated_time"),
        })
    return json.dumps({
        "conversations": output,
        "count": len(output),
        "has_more": has_more,
        "next_cursor": next_cursor if has_more else None,
    }, indent=2, ensure_ascii=False)


@mcp.tool()
async def ig_get_conversation_messages(conversation_id: str, limit: int = 10, after: str = "") -> str:
    """
    Get messages from a specific Instagram Direct conversation.

    Args:
        conversation_id: The conversation ID from ig_list_conversations
        limit: Number of messages to return (max 100, default 10)
        after: Pagination cursor for next page
    """
    params = {
        "fields": "message,from,created_time",
        "limit": min(limit, 100),
    }
    if after:
        params["after"] = after
    result = await _meta_get(f"{conversation_id}/messages", params=params)
    messages = result.get("data", [])
    next_cursor = result.get("paging", {}).get("cursors", {}).get("after", "")
    has_more = bool(result.get("paging", {}).get("next"))
    output = []
    for msg in messages:
        output.append({
            "id": msg.get("id"),
            "from": msg.get("from", {}),
            "message": msg.get("message", ""),
            "created_time": msg.get("created_time"),
        })
    return json.dumps({
        "messages": output,
        "count": len(output),
        "has_more": has_more,
        "next_cursor": next_cursor if has_more else None,
    }, indent=2, ensure_ascii=False)


# == TIKTOK (Content Posting API) ==

@mcp.tool()
async def tiktok_query_creator_info() -> str:
    """
    Query the authorized TikTok creator's info (privacy options, posting limits).
    Must be called before publishing to get allowed privacy levels.
    """
    if not TIKTOK_ACCESS_TOKEN:
        return json.dumps({"error": "TIKTOK_ACCESS_TOKEN not configured"})
    result = await _tiktok_post("post/publish/creator_info/query/", {})
    return json.dumps(result, indent=2)


@mcp.tool()
async def tiktok_publish_video(
    video_url: str,
    title: str = "",
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    disable_comment: bool = False,
    disable_duet: bool = False,
    disable_stitch: bool = False,
) -> str:
    """
    Publish a video directly to TikTok. Requires video.publish scope and audit for public visibility.

    Args:
        video_url: Public HTTPS URL of the video (domain must be verified in TikTok dev portal)
        title: Caption text (max 2200 chars, supports #hashtags and @mentions)
        privacy_level: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR, or SELF_ONLY
        disable_comment: Disable comments
        disable_duet: Disable duets
        disable_stitch: Disable stitches
    """
    if not TIKTOK_ACCESS_TOKEN:
        return json.dumps({"error": "TIKTOK_ACCESS_TOKEN not configured"})
    payload = {
        "post_info": {
            "title": title,
            "privacy_level": privacy_level,
            "disable_comment": disable_comment,
            "disable_duet": disable_duet,
            "disable_stitch": disable_stitch,
        },
        "source_info": {"source": "PULL_FROM_URL", "video_url": video_url},
    }
    result = await _tiktok_post("post/publish/video/init/", payload)
    pid = result.get("data", {}).get("publish_id")
    return json.dumps({"status": "processing", "publish_id": pid, "hint": "Use tiktok_check_publish_status to poll until PUBLISH_COMPLETE"}, indent=2)


@mcp.tool()
async def tiktok_publish_photos(
    photo_urls: list[str],
    title: str = "",
    description: str = "",
    privacy_level: str = "PUBLIC_TO_EVERYONE",
    auto_add_music: bool = True,
) -> str:
    """
    Publish a photo post (carousel) directly to TikTok.

    Args:
        photo_urls: List of public HTTPS image URLs (domain must be verified)
        title: Title for the photo post
        description: Description text (supports #hashtags and @mentions)
        privacy_level: PUBLIC_TO_EVERYONE, MUTUAL_FOLLOW_FRIENDS, FOLLOWER_OF_CREATOR, or SELF_ONLY
        auto_add_music: Let TikTok auto-add background music
    """
    if not TIKTOK_ACCESS_TOKEN:
        return json.dumps({"error": "TIKTOK_ACCESS_TOKEN not configured"})
    payload = {
        "post_info": {
            "title": title,
            "description": description,
            "privacy_level": privacy_level,
            "auto_add_music": auto_add_music,
        },
        "source_info": {"source": "PULL_FROM_URL", "photo_cover_index": 0, "photo_images": photo_urls},
        "post_mode": "DIRECT_POST",
        "media_type": "PHOTO",
    }
    result = await _tiktok_post("post/publish/content/init/", payload)
    pid = result.get("data", {}).get("publish_id")
    return json.dumps({"status": "processing", "publish_id": pid, "hint": "Use tiktok_check_publish_status to poll"}, indent=2)


@mcp.tool()
async def tiktok_upload_to_inbox(video_url: str) -> str:
    """
    Upload a video to the TikTok creator's inbox (draft) for them to review and post manually.
    Lower permission bar than direct post (video.upload scope only).

    Args:
        video_url: Public HTTPS URL of the video (domain must be verified)
    """
    if not TIKTOK_ACCESS_TOKEN:
        return json.dumps({"error": "TIKTOK_ACCESS_TOKEN not configured"})
    result = await _tiktok_post("post/publish/inbox/video/init/", {"source_info": {"source": "PULL_FROM_URL", "video_url": video_url}})
    pid = result.get("data", {}).get("publish_id")
    return json.dumps({"status": "sent_to_inbox", "publish_id": pid, "hint": "Creator will get a TikTok notification to review"}, indent=2)


@mcp.tool()
async def tiktok_check_publish_status(publish_id: str) -> str:
    """
    Check the status of a TikTok publish request.

    Args:
        publish_id: The publish_id returned from a previous publish call
    """
    if not TIKTOK_ACCESS_TOKEN:
        return json.dumps({"error": "TIKTOK_ACCESS_TOKEN not configured"})
    result = await _tiktok_post("post/publish/status/fetch/", {"publish_id": publish_id})
    return json.dumps(result, indent=2)


# == SSE Transport ==
sse = SseServerTransport("/messages/")


async def handle_sse(request: Request):
    logger.info(f"SSE connection from {request.client}")
    async with sse.connect_sse(request.scope, request.receive, request._send) as (rs, ws):
        await mcp._mcp_server.run(rs, ws, mcp._mcp_server.create_initialization_options())


async def health(request: Request):
    return JSONResponse({
        "name": "Social Publishing MCP Server",
        "status": "ok",
        "transport": "sse",
        "sse_endpoint": "/sse",
        "tools_count": 20,
        "platforms": ["facebook", "instagram", "tiktok"],
        "capabilities": ["publishing", "conversations"],
    })


app = Starlette(
    routes=[
        Route("/", endpoint=health),
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ],
    middleware=[
        Middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"], expose_headers=["*"]),
    ],
)

if __name__ == "__main__":
    logger.info(f"Starting Social Publishing MCP Server on 0.0.0.0:{PORT}")
    uvicorn.run(app, host="0.0.0.0", port=PORT, proxy_headers=True, forwarded_allow_ips="*")
