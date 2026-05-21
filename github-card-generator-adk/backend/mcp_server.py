"""
MCP Server for GitHub Dev Card Generator
Tools: scrape_github, analyze_profile, generate_card_html, save_card
"""

import os
import json
import httpx
from pathlib import Path
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("github-card-generator")

STATIC_DIR = Path(__file__).parent / "static" / "cards"
STATIC_DIR.mkdir(parents=True, exist_ok=True)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

THEME_STYLES = {
    "hacker": {
        "bg": "#0d0d0d",
        "card_bg": "#111111",
        "accent": "#00ff41",
        "text": "#cccccc",
        "badge_bg": "#003300",
        "badge_text": "#00ff41",
        "border": "#00ff41",
        "font": "'Courier New', monospace",
        "repo_bg": "#0a0a0a",
    },
    "builder": {
        "bg": "#f0f4f8",
        "card_bg": "#ffffff",
        "accent": "#3b82f6",
        "text": "#1e293b",
        "badge_bg": "#dbeafe",
        "badge_text": "#1d4ed8",
        "border": "#93c5fd",
        "font": "'Segoe UI', sans-serif",
        "repo_bg": "#f8fafc",
    },
    "researcher": {
        "bg": "#1a1a2e",
        "card_bg": "#16213e",
        "accent": "#e94560",
        "text": "#e0e0e0",
        "badge_bg": "#0f3460",
        "badge_text": "#e94560",
        "border": "#e94560",
        "font": "'Georgia', serif",
        "repo_bg": "#0f3460",
    },
    "designer": {
        "bg": "#fdf4ff",
        "card_bg": "#ffffff",
        "accent": "#a855f7",
        "text": "#3b0764",
        "badge_bg": "#f3e8ff",
        "badge_text": "#7c3aed",
        "border": "#d8b4fe",
        "font": "'Trebuchet MS', sans-serif",
        "repo_bg": "#faf5ff",
    },
    "open-source-hero": {
        "bg": "#0f172a",
        "card_bg": "#1e293b",
        "accent": "#f59e0b",
        "text": "#e2e8f0",
        "badge_bg": "#292524",
        "badge_text": "#f59e0b",
        "border": "#f59e0b",
        "font": "'Verdana', sans-serif",
        "repo_bg": "#0f172a",
    },
}


@mcp.tool()
async def scrape_github(username: str) -> dict:
    """
    Scrape public GitHub profile data for a given username.
    Returns name, bio, location, public_repos, followers, top repos, and language breakdown.
    """
    async with httpx.AsyncClient(timeout=15.0) as client:
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        github_token = os.getenv("GITHUB_TOKEN", "")
        if github_token:
            headers["Authorization"] = f"Bearer {github_token}"

        # Fetch user profile
        user_resp = await client.get(f"https://api.github.com/users/{username}", headers=headers)
        if user_resp.status_code == 404:
            return {"error": f"GitHub user '{username}' not found."}
        if user_resp.status_code != 200:
            return {"error": f"GitHub API error: {user_resp.status_code}"}

        user = user_resp.json()

        # Fetch repos sorted by stars
        repos_resp = await client.get(
            f"https://api.github.com/users/{username}/repos",
            headers=headers,
            params={"sort": "stars", "direction": "desc", "per_page": 30},
        )
        repos = repos_resp.json() if repos_resp.status_code == 200 else []

        # Build top 6 repos
        top_repos = []
        lang_counts: dict[str, int] = {}
        for repo in repos:
            if repo.get("fork"):
                continue
            lang = repo.get("language") or "Unknown"
            lang_counts[lang] = lang_counts.get(lang, 0) + (repo.get("stargazers_count") or 0) + 1
            if len(top_repos) < 6:
                top_repos.append(
                    {
                        "name": repo.get("name", ""),
                        "stars": repo.get("stargazers_count", 0),
                        "language": lang,
                        "description": repo.get("description") or "",
                        "url": repo.get("html_url", ""),
                    }
                )

        # Sort languages by count
        sorted_langs = sorted(lang_counts.items(), key=lambda x: x[1], reverse=True)
        most_used_languages = [lang for lang, _ in sorted_langs[:6] if lang != "Unknown"]

        return {
            "username": username,
            "name": user.get("name") or username,
            "bio": user.get("bio") or "",
            "location": user.get("location") or "",
            "avatar_url": user.get("avatar_url", ""),
            "profile_url": user.get("html_url", f"https://github.com/{username}"),
            "public_repos": user.get("public_repos", 0),
            "followers": user.get("followers", 0),
            "following": user.get("following", 0),
            "top_repos": top_repos,
            "most_used_languages": most_used_languages,
            "company": user.get("company") or "",
            "blog": user.get("blog") or "",
            "created_at": user.get("created_at", ""),
        }


@mcp.tool()
async def analyze_profile(github_data: dict) -> dict:
    """
    Use Gemini 2.5 Flash to analyze a GitHub profile and produce a dev personality card.
    Returns developer_vibe, top_skills, fun_fact, and card_theme.
    """
    if not GEMINI_API_KEY:
        # Fallback analysis without AI
        langs = github_data.get("most_used_languages", ["Code"])
        return {
            "developer_vibe": f"A passionate developer who loves building with {', '.join(langs[:2]) if langs else 'code'}.",
            "top_skills": langs[:3] if langs else ["Programming", "Open Source", "Problem Solving"],
            "fun_fact": f"Has {github_data.get('public_repos', 0)} public repos and {github_data.get('followers', 0)} followers on GitHub.",
            "card_theme": "builder",
        }

    prompt = f"""
You are a witty, insightful developer profile analyst. Analyze this GitHub profile data and respond ONLY with a valid JSON object (no markdown, no explanation):

Profile data:
{json.dumps(github_data, indent=2)}

Respond with exactly this JSON structure:
{{
  "developer_vibe": "A single punchy sentence capturing this developer's personality and style (max 15 words, make it creative and fun)",
  "top_skills": ["skill1", "skill2", "skill3"],
  "fun_fact": "One clever, specific observation inferred from their repos or stats (make it interesting, not generic)",
  "card_theme": "one of: hacker, builder, researcher, designer, open-source-hero"
}}

card_theme guide:
- hacker: systems/security/low-level/kernel work
- builder: full-stack/web/apps/products
- researcher: ML/AI/data science/academic
- designer: UI/UX/creative/frontend-heavy
- open-source-hero: massive OSS contributions/many repos/popular projects
"""

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json={"contents": [{"parts": [{"text": prompt}]}]},
        )
        if resp.status_code != 200:
            # Fallback
            langs = github_data.get("most_used_languages", ["Code"])
            return {
                "developer_vibe": f"A dedicated developer crafting solutions with {', '.join(langs[:2]) if langs else 'passion'}.",
                "top_skills": langs[:3] if langs else ["Programming", "Open Source", "Collaboration"],
                "fun_fact": f"Maintains {github_data.get('public_repos', 0)} repos with {github_data.get('followers', 0)} followers.",
                "card_theme": "builder",
            }

        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip markdown fences if present
        text = text.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        text = text.strip()
        return json.loads(text)


@mcp.tool()
async def generate_card_html(username: str, github_data: dict, analysis: dict) -> str:
    """
    Generate a beautiful, self-contained HTML dev card from GitHub data and AI analysis.
    Returns an HTML string ready to save or display.
    """
    theme_key = analysis.get("card_theme", "builder")
    theme = THEME_STYLES.get(theme_key, THEME_STYLES["builder"])

    name = github_data.get("name", username)
    bio = github_data.get("bio", "")
    location = github_data.get("location", "")
    avatar_url = github_data.get("avatar_url", "")
    public_repos = github_data.get("public_repos", 0)
    followers = github_data.get("followers", 0)
    following = github_data.get("following", 0)
    profile_url = github_data.get("profile_url", f"https://github.com/{username}")
    top_repos = github_data.get("top_repos", [])[:3]
    languages = github_data.get("most_used_languages", [])[:5]

    vibe = analysis.get("developer_vibe", "")
    top_skills = analysis.get("top_skills", [])
    fun_fact = analysis.get("fun_fact", "")

    # Build badges
    skill_badges = "".join(
        f'<span class="badge">{skill}</span>' for skill in top_skills
    )

    # Build language tags
    lang_tags = "".join(
        f'<span class="lang-tag">{lang}</span>' for lang in languages
    )

    # Build repo cards
    repo_cards_html = ""
    for repo in top_repos:
        stars = repo.get("stars", 0)
        star_display = f"★ {stars}" if stars > 0 else "★ 0"
        lang = repo.get("language", "")
        desc = repo.get("description", "") or "No description"
        if len(desc) > 60:
            desc = desc[:57] + "..."
        repo_cards_html += f"""
        <a class="repo-card" href="{repo.get('url', '#')}" target="_blank">
            <div class="repo-header">
                <span class="repo-name">📁 {repo.get('name', '')}</span>
                <span class="repo-stars">{star_display}</span>
            </div>
            <p class="repo-desc">{desc}</p>
            {f'<span class="repo-lang">{lang}</span>' if lang else ''}
        </a>"""

    # Theme label
    theme_labels = {
        "hacker": "⚡ HACKER",
        "builder": "🔨 BUILDER",
        "researcher": "🔬 RESEARCHER",
        "designer": "🎨 DESIGNER",
        "open-source-hero": "🦸 OSS HERO",
    }
    theme_label = theme_labels.get(theme_key, "💻 DEVELOPER")

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{name} — Dev Card</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;700&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: {theme['bg']};
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    font-family: {theme['font']};
  }}

  .card {{
    background: {theme['card_bg']};
    border: 2px solid {theme['border']};
    border-radius: 16px;
    width: 100%;
    max-width: 480px;
    padding: 28px;
    box-shadow: 0 0 40px {theme['accent']}22, 0 8px 32px rgba(0,0,0,0.4);
    animation: fadeIn 0.6s ease;
    position: relative;
    overflow: hidden;
  }}

  .card::before {{
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, transparent, {theme['accent']}, transparent);
  }}

  @keyframes fadeIn {{
    from {{ opacity: 0; transform: translateY(16px); }}
    to {{ opacity: 1; transform: translateY(0); }}
  }}

  .theme-label {{
    display: inline-block;
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.15em;
    color: {theme['accent']};
    background: {theme['badge_bg']};
    border: 1px solid {theme['accent']};
    border-radius: 4px;
    padding: 3px 8px;
    margin-bottom: 20px;
  }}

  .profile-row {{
    display: flex;
    align-items: flex-start;
    gap: 16px;
    margin-bottom: 20px;
  }}

  .avatar {{
    width: 72px;
    height: 72px;
    border-radius: 50%;
    border: 2px solid {theme['accent']};
    flex-shrink: 0;
    object-fit: cover;
  }}

  .profile-info {{ flex: 1; min-width: 0; }}

  .name {{
    font-family: 'Syne', sans-serif;
    font-size: 22px;
    font-weight: 800;
    color: {theme['accent']};
    line-height: 1.2;
    margin-bottom: 2px;
  }}

  .username {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    color: {theme['text']}99;
    margin-bottom: 6px;
  }}

  .location {{
    font-size: 12px;
    color: {theme['text']}88;
  }}

  .vibe {{
    font-size: 13px;
    color: {theme['text']};
    line-height: 1.6;
    border-left: 3px solid {theme['accent']};
    padding-left: 12px;
    margin-bottom: 18px;
    font-style: italic;
  }}

  .skills-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 6px;
    margin-bottom: 18px;
  }}

  .badge {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
    background: {theme['badge_bg']};
    color: {theme['badge_text']};
    border: 1px solid {theme['accent']}55;
    border-radius: 6px;
    padding: 4px 10px;
  }}

  .stats-row {{
    display: flex;
    gap: 0;
    margin-bottom: 18px;
    border: 1px solid {theme['border']}44;
    border-radius: 10px;
    overflow: hidden;
  }}

  .stat {{
    flex: 1;
    text-align: center;
    padding: 10px 4px;
    border-right: 1px solid {theme['border']}33;
  }}

  .stat:last-child {{ border-right: none; }}

  .stat-num {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 18px;
    font-weight: 700;
    color: {theme['accent']};
    display: block;
  }}

  .stat-label {{
    font-size: 10px;
    color: {theme['text']}77;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }}

  .section-title {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 0.12em;
    color: {theme['text']}66;
    text-transform: uppercase;
    margin-bottom: 8px;
  }}

  .repos {{ margin-bottom: 16px; }}

  .repo-card {{
    display: block;
    text-decoration: none;
    background: {theme['repo_bg']};
    border: 1px solid {theme['border']}33;
    border-radius: 8px;
    padding: 10px 12px;
    margin-bottom: 7px;
    transition: border-color 0.2s, transform 0.2s;
  }}

  .repo-card:hover {{
    border-color: {theme['accent']};
    transform: translateX(3px);
  }}

  .repo-header {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 4px;
  }}

  .repo-name {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 700;
    color: {theme['accent']};
  }}

  .repo-stars {{
    font-size: 11px;
    color: {theme['text']}88;
  }}

  .repo-desc {{
    font-size: 11px;
    color: {theme['text']}88;
    line-height: 1.4;
    margin-bottom: 5px;
  }}

  .repo-lang {{
    font-size: 10px;
    background: {theme['badge_bg']};
    color: {theme['badge_text']};
    padding: 2px 6px;
    border-radius: 4px;
    font-family: 'JetBrains Mono', monospace;
  }}

  .langs-row {{
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    margin-bottom: 18px;
  }}

  .lang-tag {{
    font-size: 10px;
    font-family: 'JetBrains Mono', monospace;
    background: {theme['repo_bg']};
    color: {theme['text']}99;
    border: 1px solid {theme['border']}33;
    padding: 3px 8px;
    border-radius: 20px;
  }}

  .fun-fact {{
    font-size: 11px;
    color: {theme['text']}88;
    background: {theme['repo_bg']};
    border-radius: 8px;
    padding: 10px 12px;
    line-height: 1.5;
    margin-bottom: 18px;
    border-left: 3px solid {theme['accent']}66;
  }}

  .footer {{
    text-align: center;
    border-top: 1px solid {theme['border']}22;
    padding-top: 14px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }}

  .gh-link {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    color: {theme['accent']};
    text-decoration: none;
    opacity: 0.8;
    transition: opacity 0.2s;
  }}

  .gh-link:hover {{ opacity: 1; }}

  .watermark {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 10px;
    color: {theme['text']}33;
  }}
</style>
</head>
<body>
<div class="card">
  <div class="theme-label">{theme_label}</div>

  <div class="profile-row">
    <img class="avatar" src="{avatar_url}" alt="{name}" onerror="this.src='https://github.com/identicons/{username}.png'">
    <div class="profile-info">
      <div class="name">{name}</div>
      <div class="username">@{username}</div>
      {f'<div class="location">📍 {location}</div>' if location else ''}
    </div>
  </div>

  {f'<div class="vibe">"{vibe}"</div>' if vibe else ''}

  <div class="skills-row">
    {skill_badges}
  </div>

  <div class="stats-row">
    <div class="stat">
      <span class="stat-num">{public_repos}</span>
      <span class="stat-label">Repos</span>
    </div>
    <div class="stat">
      <span class="stat-num">{followers}</span>
      <span class="stat-label">Followers</span>
    </div>
    <div class="stat">
      <span class="stat-num">{following}</span>
      <span class="stat-label">Following</span>
    </div>
  </div>

  {f'<div class="repos"><div class="section-title">▶ Top Repos</div>{repo_cards_html}</div>' if repo_cards_html else ''}

  {f'<div><div class="section-title">▶ Languages</div><div class="langs-row">{lang_tags}</div></div>' if lang_tags else ''}

  {f'<div class="fun-fact">💡 {fun_fact}</div>' if fun_fact else ''}

  <div class="footer">
    <a class="gh-link" href="{profile_url}" target="_blank">github.com/{username} →</a>
    <span class="watermark">DevCard Generator</span>
  </div>
</div>
</body>
</html>"""

    return html


@mcp.tool()
async def save_card(username: str, html: str) -> str:
    """
    Save the generated HTML card to disk and return the URL path.
    """
    filename = STATIC_DIR / f"{username}.html"
    filename.write_text(html, encoding="utf-8")
    return f"/card/{username}"


if __name__ == "__main__":
    mcp.run(transport="stdio")
