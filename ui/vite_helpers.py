import os
import json
from flask import current_app, url_for
from markupsafe import Markup

VITE_MANIFEST_PATH = 'ui/static/dist/vite/manifest.json'
VITE_DEV_SERVER_URL = 'http://localhost:5173' # Default Vite dev server

def vite_asset(path, asset_type='script'):
    """
    Generates an HTML tag for a Vite asset.
    In development, it points to the Vite dev server.
    In production, it points to the compiled asset using the manifest.
    """
    if current_app.config.get('FLASK_ENV') == 'development':
        # Development: Serve directly from Vite dev server
        # The path needs to be relative to the Vite root, which is the project root.
        # So, 'ui/static/js/main.js' becomes '/ui/static/js/main.js' for the dev server.
        dev_url = f"{VITE_DEV_SERVER_URL}/{path.lstrip('/')}"
        if asset_type == 'script':
            # Add @vite/client for HMR in development
            hmr_client = f'<script type="module" src="{VITE_DEV_SERVER_URL}/@vite/client"></script>'
            return Markup(f"{hmr_client}\n    <script type=\"module\" src=\"{dev_url}\"></script>")
        elif asset_type == 'style':
            # In dev, CSS is usually injected by JS, but if a direct link is needed:
            return Markup(f'<link rel="stylesheet" href="{dev_url}">')
        return '' # Should not happen for known types
    else:
        # Production: Use manifest.json
        manifest = {}
        try:
            with open(VITE_MANIFEST_PATH) as f:
                manifest = json.load(f)
        except FileNotFoundError:
            current_app.logger.error(f"Vite manifest.json not found at {VITE_MANIFEST_PATH}")
            return ''
        except json.JSONDecodeError:
            current_app.logger.error(f"Error decoding Vite manifest.json at {VITE_MANIFEST_PATH}")
            return ''

        if path not in manifest:
            current_app.logger.error(f"Asset '{path}' not found in Vite manifest.")
            return ''

        manifest_entry = manifest[path]
        asset_url = url_for('static', filename=f"dist/vite/{manifest_entry['file']}")
        
        tags = []
        if asset_type == 'script':
            tags.append(f'<script type="module" src="{asset_url}"></script>')
        elif asset_type == 'style':
            tags.append(f'<link rel="stylesheet" href="{asset_url}">')

        # Handle CSS imports from JS entry points in production
        if 'css' in manifest_entry:
            for css_file_path in manifest_entry['css']:
                css_url = url_for('static', filename=f"dist/vite/{css_file_path}")
                tags.append(f'<link rel="stylesheet" href="{css_url}">')
        
        return Markup('\n    '.join(tags))

def vite_script(path):
    """Helper for JS assets."""
    return vite_asset(path, asset_type='script')

def vite_style(path):
    """Helper for CSS assets (if directly linked, usually handled by JS import)."""
    # In Vite, CSS is typically imported into JS. 
    # This helper is for cases where a direct CSS link from the manifest might be needed,
    # but usually, the CSS for an entry point is handled by vite_asset when asset_type='script'.
    # For production, manifest[path]['css'] lists CSS files associated with a JS entry.
    # This function might be less used if all CSS is bundled via JS.
    if current_app.config.get('FLASK_ENV') == 'development':
        dev_url = f"{VITE_DEV_SERVER_URL}/{path.lstrip('/')}"
        return Markup(f'<link rel="stylesheet" href="{dev_url}">')
    else:
        # In production, CSS is typically linked via the JS entry's manifest.
        # This function would need to look up the specific CSS file in the manifest.
        # However, the main `vite_asset` for a script entry already handles its CSS.
        # This is a placeholder if direct CSS linking from manifest is ever needed differently.
        manifest = {}
        try:
            with open(VITE_MANIFEST_PATH) as f:
                manifest = json.load(f)
        except FileNotFoundError:
            return '' # Manifest not found
        
        # Find the CSS file in the manifest (this logic might need refinement based on how CSS is structured)
        # This assumes 'path' is the direct key to a CSS asset in the manifest, which might not be the case.
        if path in manifest and manifest[path].get('isEntry', False) == False and manifest[path]['file'].endswith('.css'):
             asset_url = url_for('static', filename=f"dist/vite/{manifest[path]['file']}")
             return Markup(f'<link rel="stylesheet" href="{asset_url}">')
        return '' # Asset not found or not a CSS entry
