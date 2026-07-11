import logging
import xmltodict
import httpx
from models import db, Package, PypiQueue
from pypi_utils import process_and_get_package_details

logger = logging.getLogger(__name__)

def fetch_rss_updates():
    """
    Synchronize package records with the latest PyPI RSS updates.

    Returns:
        int: The number of packages updated or added, or 0 if processing fails.
    """
    rss_url = "https://pypi.org/rss/updates.xml"
    try:
        r = httpx.get(rss_url, timeout=10.0)
        if r.status_code == 200:
            parsed = xmltodict.parse(r.text)
            rss = parsed.get("rss", {})
            channel = rss.get("channel", {})
            items = channel.get("item", [])

            if not isinstance(items, list):
                items = [items]

            updated_count = 0
            for item in items:
                title = item.get("title", "")
                # RSS titles are usually "package-name version" or "package-name (version)"
                # Let's extract the package name (the first word)
                parts = title.split()
                if not parts:
                    continue
                package_name = parts[0]

                # Check if package is already in Package table or rejected queue
                pkg = Package.query.filter_by(name=package_name).first()
                if pkg:
                    # Update details
                    details = process_and_get_package_details(package_name)
                    if details:
                        pkg.version = details["version"]
                        pkg.author = details["author"]
                        pkg.description = details["description"]
                        pkg.github_url = details["github_url"]
                        pkg.total_downloads = details["total_downloads"]
                        pkg.github_stars = details["github_stars"]
                        pkg.license = details["license"]
                        db.session.commit()
                        updated_count += 1
                else:
                    # Check if it was rejected before
                    q_item = PypiQueue.query.filter_by(name=package_name).first()
                    if q_item and q_item.status == 'rejected':
                        continue

                    # New package from RSS, let's fetch details and check filter
                    details = process_and_get_package_details(package_name)
                    if details:
                        new_pkg = Package(
                            name=details["name"],
                            author=details["author"],
                            version=details["version"],
                            description=details["description"],
                            github_url=details["github_url"],
                            pypi_url=details["pypi_url"],
                            total_downloads=details["total_downloads"],
                            github_stars=details["github_stars"],
                            license=details["license"]
                        )
                        db.session.add(new_pkg)

                        # Update queue if it exists
                        if q_item:
                            q_item.status = 'fetched'
                        else:
                            db.session.add(PypiQueue(name=package_name, status='fetched'))
                        db.session.commit()
                        updated_count += 1
                    else:
                        # Low quality, flag as rejected
                        if q_item:
                            q_item.status = 'rejected'
                        else:
                            db.session.add(PypiQueue(name=package_name, status='rejected'))
                        db.session.commit()

            logger.info(f"RSS Polling Complete: updated/added {updated_count} packages")
            return updated_count
    except Exception as e:
        logger.error(f"Error checking RSS updates: {e}")
        return 0
