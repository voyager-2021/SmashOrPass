import re
import urllib.parse
import httpx
import logging

logger = logging.getLogger(__name__)

def clean_description(desc):
    """
    Normalize a package description by removing surrounding whitespace.
    
    Parameters:
    	desc: The description text to normalize.
    
    Returns:
    	str: The stripped description, or an empty string when no description is provided.
    """
    if not desc:
        return ""
    # strip HTML/Markdown if needed or just return stripped
    return desc.strip()

def parse_github_repo(project_urls, home_page=None):
    """
    Extract a normalized GitHub repository owner and name from project URLs.
    
    Parameters:
        project_urls (dict): Mapping whose values may contain GitHub repository URLs.
        home_page (str, optional): Additional URL to inspect.
    
    Returns:
        tuple or None: A `(owner, repository)` pair, or `None` if no GitHub repository URL is found.
    """
    urls = []
    if project_urls and isinstance(project_urls, dict):
        urls.extend(project_urls.values())
    if home_page:
        urls.append(home_page)

    pattern = re.compile(r'github\.com/([^/]+)/([^/]+)')
    for url in urls:
        if not url or not isinstance(url, str):
            continue
        match = pattern.search(url)
        if match:
            owner = match.group(1)
            repo = match.group(2)
            # Remove trailing slashes or subpages (e.g., .git, /issues)
            if repo.endswith('.git'):
                repo = repo[:-4]
            repo = repo.split('/')[0]
            owner = owner.split('@')[0] # fix any weird git ssh formats
            return owner, repo
    return None

def fetch_github_stars(owner, repo):
    """
    Retrieve the number of stars for a GitHub repository.
    
    Parameters:
    	owner (str): GitHub repository owner.
    	repo (str): GitHub repository name.
    
    Returns:
    	int: The repository's star count, or 0 if the request fails or the repository data does not include a star count.
    """
    url = f"https://api.github.com/repos/{owner}/{repo}"
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "SmashOrPass-App/1.0"
    }
    try:
        r = httpx.get(url, headers=headers, timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            return data.get("stargazers_count", 0)
    except Exception as e:
        logger.warning(f"Failed to fetch GitHub stars for {owner}/{repo}: {e}")
    return 0

def fetch_pypi_downloads(package_name):
    """Fetch the number of downloads for a package during the previous month.
    
    Parameters:
        package_name: The PyPI package name.
    
    Returns:
        The package's previous-month download count, or 0 if the request fails or provides no count.
    """
    url = f"https://pypistats.org/api/packages/{package_name}/recent"
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 200:
            data = r.json()
            # PyPI Stats API format: {"data": {"last_day": 10, "last_week": 70, "last_month": 300}, "package": "...", "type": "recent_downloads"}
            recent_data = data.get("data", {})
            return recent_data.get("last_month", 0)
    except Exception as e:
        logger.warning(f"Failed to fetch downloads for {package_name}: {e}")
    return 0

def fetch_pypi_metadata(package_name):
    """
    Retrieve metadata for a package from the PyPI JSON API.
    
    Parameters:
        package_name (str): The PyPI package name.
    
    Returns:
        dict: The package metadata, or None if the request fails or the package is unavailable.
    """
    url = f"https://pypi.org/pypi/{package_name}/json"
    try:
        r = httpx.get(url, timeout=5.0)
        if r.status_code == 200:
            return r.json()
    except Exception as e:
        logger.warning(f"Error fetching metadata for {package_name}: {e}")
    return None

def is_low_quality(info):
    """
    Assess whether package metadata appears likely to represent a low-quality or spam-like package.
    
    Parameters:
        info (dict): Package metadata containing the name, description, summary, and version.
    
    Returns:
        bool: `True` if the metadata is likely low quality, `False` otherwise.
    """
    if not info:
        return True

    name = info.get("name", "")
    description = info.get("description", "")
    summary = info.get("summary", "")
    version = info.get("version", "")

    # Check 1: Empty or extremely short name
    if not name or len(name) < 2:
        return True

    # Check 2: No description and no summary
    desc_content = (description or "").strip()
    sum_content = (summary or "").strip()

    # If the description or summary are identical to name or just placeholders
    combined = (desc_content + " " + sum_content).lower()

    if len(desc_content) < 15 and len(sum_content) < 15:
        # Very short metadata
        return True

    # Check 3: Placeholder phrases
    placeholders = [
        "add a short description",
        "a short description of the package",
        "work in progress",
        "todo:",
        "to be done",
        "placeholder",
        "test package",
        "for testing purposes",
        "package description goes here"
    ]
    for ph in placeholders:
        if ph in combined:
            return True

    # Check 4: Version is ultra early but description is too minimal
    if version in ["0.0.0", "0.0.1", "0.1.0"] and len(desc_content) < 30:
        return True

    # Check 5: Pure punctuation/gibberish name
    if not re.match(r'^[a-zA-Z0-9_\-\.]+$', name):
        return True

    return False

def process_and_get_package_details(package_name):
    """
    Fetch, filter, and assemble selected details for a PyPI package.
    
    Parameters:
        package_name (str): The package name to retrieve.
    
    Returns:
        dict or None: A package details record, or None if metadata cannot be
        retrieved or the package is classified as low quality.
    """
    metadata = fetch_pypi_metadata(package_name)
    if not metadata:
        return None

    info = metadata.get("info", {})
    if is_low_quality(info):
        return None

    desc = info.get("description", "") or info.get("summary", "") or ""
    # if description is too long (some readme files are massive), keep first 10000 characters
    if len(desc) > 10000:
        desc = desc[:10000] + "\n\n... (description truncated)"

    pypi_url = info.get("project_url") or f"https://pypi.org/project/{package_name}/"

    # GitHub integration
    github_url = None
    stars = 0
    repo_info = parse_github_repo(info.get("project_urls"), info.get("home_page"))
    if repo_info:
        owner, repo = repo_info
        github_url = f"https://github.com/{owner}/{repo}"
        stars = fetch_github_stars(owner, repo)

    # Download stats
    downloads = fetch_pypi_downloads(package_name)

    return {
        "name": info.get("name", package_name),
        "author": info.get("author") or "Unknown",
        "version": info.get("version") or "0.0.0",
        "description": clean_description(desc),
        "github_url": github_url,
        "pypi_url": pypi_url,
        "total_downloads": downloads,
        "github_stars": stars,
        "license": info.get("license") or "None specified"
    }

def fetch_simple_api_names():
    """
    Fetch all package names from PyPI simple API.
    Returns list of names.
    """
    url = "https://pypi.org/simple/"
    headers = {
        "Accept": "application/vnd.pypi.simple.v1+json"
    }
    try:
        r = httpx.get(url, headers=headers, timeout=15.0)
        if r.status_code == 200:
            data = r.json()
            projects = data.get("projects", [])
            names = []
            for p in projects:
                if isinstance(p, dict) and "name" in p:
                    names.append(p["name"])
                elif isinstance(p, str):
                    names.append(p)
            return names
    except Exception as e:
        logger.error(f"Failed to fetch /simple/ index: {e}")
    return []
