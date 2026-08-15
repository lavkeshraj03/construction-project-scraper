"""server.py — Simple HTTP server with HTML entry form to add manual construction projects.

Usage:
    python3 server.py

Open browser at:
    http://localhost:8000
"""

from __future__ import annotations

import html
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# Ensure app package is importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import (
    all_projects,
    all_scrape_runs,
    get_session,
    init_db,
    upsert_project,
)
from app.exporters.excel import export_to_excel
from app.processors.classifier import classify_materials, classify_project_type
import os
from app.processors.normalizer import normalize
from app.processors.scorer import calculate_lead_score
from app.utils.logger import get_logger

log = get_logger("server")

PORT = int(os.environ.get("PORT", 8000))


HTML_FORM = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Add Construction Project — Granite Lead System</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f3f4f6; margin: 0; padding: 30px; color: #1f2937;">

    <div style="max-width: 850px; margin: 0 auto; background: #ffffff; padding: 35px; border-radius: 12px; box-shadow: 0 4px 15px rgba(0, 0, 0, 0.08); border: 1px solid #e5e7eb;">
        
        <div style="border-bottom: 2px solid #1f3864; padding-bottom: 15px; margin-bottom: 25px;">
            <h1 style="color: #1f3864; margin: 0; font-size: 24px;">Phase 1: Manual Project Data Entry (16 Fields)</h1>
            <p style="color: #6b7280; margin-top: 6px; font-size: 14px;">Fill this form to manually add a project. Submitting automatically normalises, saves to SQLite, and appends to <b>construction_projects.xlsx</b>.</p>
        </div>

        {notification}

        <form method="POST" action="/submit">
            
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">1. Builder Name *</label>
                    <input type="text" name="builder_name" required placeholder="e.g. Godrej Properties" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">2. Project Name *</label>
                    <input type="text" name="project_name" required placeholder="e.g. Godrej Skyline" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">3. Location *</label>
                    <input type="text" name="location" required placeholder="e.g. Koregaon Park, Pune" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">4. Project Value (₹)</label>
                    <input type="text" name="project_value" placeholder="e.g. 45000000 or ₹ 4.5 Cr" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">5. Decision Maker</label>
                    <input type="text" name="decision_maker" placeholder="e.g. Rajesh Sharma" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">6. Mobile Number</label>
                    <input type="text" name="mobile" placeholder="e.g. 9876543210" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">7. Email Address</label>
                    <input type="email" name="email" placeholder="e.g. contact@godrej.com" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">8. Architect</label>
                    <input type="text" name="architect" placeholder="e.g. Ar. Sanjay Puri" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">9. Contractor</label>
                    <input type="text" name="contractor" placeholder="e.g. L&T Construction" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 2fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">10. Builder / Architect / Contractor (Optional Override)</label>
                    <input type="text" name="builder_architect_contractor" placeholder="Leave empty to auto-combine from fields 1, 8 & 9" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">11. Current Stage</label>
                    <select name="current_stage" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px; background: #fff;">
                        <option value="Under Construction">Under Construction</option>
                        <option value="Advanced Construction">Advanced Construction</option>
                        <option value="Near Completion">Near Completion</option>
                        <option value="Planning">Planning</option>
                        <option value="Approved">Approved</option>
                        <option value="Pre-Construction">Pre-Construction</option>
                        <option value="Completed">Completed</option>
                        <option value="Unknown">Unknown</option>
                    </select>
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin-bottom: 20px;">
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">12. Lead Score (0-100)</label>
                    <input type="number" name="lead_score" placeholder="Leave empty for auto score" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">13. Expected Order Value</label>
                    <input type="text" name="expected_order_value" value="Not Calculated" placeholder="e.g. Not Calculated or ₹ 15 Lakhs" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
                <div>
                    <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">14. Competition</label>
                    <input type="text" name="competition" value="Unknown" placeholder="e.g. Unknown or Nitco" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px;">
                </div>
            </div>

            <div style="background: #f9fafb; border: 1px solid #e5e7eb; padding: 15px; border-radius: 8px; margin-bottom: 25px;">
                <div style="display: grid; grid-template-columns: 1fr 2fr; gap: 20px; align-items: center;">
                    <div>
                        <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 6px;">15. Material Required?</label>
                        <select name="material_required" style="width: 100%; padding: 10px; border: 1px solid #d1d5db; border-radius: 6px; box-sizing: border-box; font-size: 14px; background: #fff;">
                            <option value="Yes">Yes</option>
                            <option value="No">No</option>
                            <option value="Unknown">Unknown</option>
                        </select>
                    </div>
                    <div>
                        <label style="display: block; font-weight: 600; font-size: 13px; color: #374151; margin-bottom: 8px;">16. Material Categories:</label>
                        <div style="display: flex; gap: 15px; flex-wrap: wrap;">
                            <label style="font-size: 14px; cursor: pointer;"><input type="checkbox" name="categories" value="Granite" checked> Granite</label>
                            <label style="font-size: 14px; cursor: pointer;"><input type="checkbox" name="categories" value="Marble"> Marble</label>
                            <label style="font-size: 14px; cursor: pointer;"><input type="checkbox" name="categories" value="Quartz"> Quartz</label>
                            <label style="font-size: 14px; cursor: pointer;"><input type="checkbox" name="categories" value="Kota"> Kota</label>
                        </div>
                    </div>
                </div>
            </div>

            <div style="text-align: right;">
                <button type="submit" style="background-color: #1f3864; color: #ffffff; border: none; padding: 12px 28px; font-size: 15px; font-weight: 600; border-radius: 6px; cursor: pointer; box-shadow: 0 2px 5px rgba(0,0,0,0.15);">
                    💾 Save Project & Update Excel
                </button>
            </div>

        </form>
    </div>

</body>
</html>
"""


class RequestHandler(BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()

            query = urllib.parse.urlparse(self.path).query
            params = urllib.parse.parse_qs(query)
            
            notification = ""
            if "saved" in params:
                pid = html.escape(params["saved"][0])
                notification = f"""
                <div style="background-color: #d1fae5; border: 1px solid #10b981; color: #065f46; padding: 14px; border-radius: 6px; margin-bottom: 20px; font-size: 14px;">
                    ✅ <b>Project Successfully Saved & Appended!</b><br>
                    Project ID: <code>{pid}</code><br>
                    Excel File (<code>output/construction_projects.xlsx</code>) has been automatically updated.
                </div>
                """

            rendered = HTML_FORM.replace("{notification}", notification)
            self.wfile.write(rendered.encode("utf-8"))
        else:
            self.send_error(404, "Page Not Found")

    def do_POST(self):
        if self.path == "/submit":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length).decode("utf-8")
            form_data = urllib.parse.parse_qs(body)

            categories = form_data.get("categories", [])
            categories_str = ", ".join(categories) if categories else ""

            raw_record = {
                "source": "Manual Entry",
                "source_url": "Web Form (Local Entry)",
                "builder_name": form_data.get("builder_name", [""])[0],
                "project_name": form_data.get("project_name", [""])[0],
                "location": form_data.get("location", [""])[0],
                "project_value": form_data.get("project_value", [""])[0],
                "decision_maker": form_data.get("decision_maker", [""])[0],
                "mobile": form_data.get("mobile", [""])[0],
                "email": form_data.get("email", [""])[0],
                "architect": form_data.get("architect", [""])[0],
                "contractor": form_data.get("contractor", [""])[0],
                "current_stage": form_data.get("current_stage", ["Unknown"])[0],
                "expected_order_value": form_data.get("expected_order_value", ["Not Calculated"])[0],
                "competition": form_data.get("competition", ["Unknown"])[0],
                "material_required": form_data.get("material_required", ["Unknown"])[0],
                "material_categories": categories_str,
                "confidence_score": "High",
            }

            # Optional manual overrides if user typed them into fields 10 or 12
            manual_bac = form_data.get("builder_architect_contractor", [""])[0].strip()
            manual_score = form_data.get("lead_score", [""])[0].strip()

            init_db()
            session = get_session()

            norm = normalize(raw_record)
            norm = classify_materials(norm)
            norm = classify_project_type(norm)

            if manual_score and manual_score.isdigit():
                norm["lead_score"] = int(manual_score)
            else:
                norm = calculate_lead_score(norm)

            if manual_bac:
                norm["builder_architect_contractor"] = manual_bac

            # Upsert into database
            _, project_id = upsert_project(session, norm)

            # Re-export updated database to Excel
            all_proj = all_projects(session)
            all_runs = all_scrape_runs(session)
            export_to_excel(all_proj, all_runs)

            log.info("Manual entry added: %s and Excel updated.", project_id)

            self.send_response(303)
            self.send_header("Location", f"/?saved={urllib.parse.quote(project_id)}")
            self.end_headers()
        else:
            self.send_error(404, "Route Not Found")


def main():
    init_db()
    server = HTTPServer(("0.0.0.0", PORT), RequestHandler)
    print("\n" + "=" * 60)
    print(f"🚀 Granite Project Entry Web Form Running at: http://localhost:{PORT}")
    print("Submit manual projects through your browser to immediately update Excel!")
    print("=" * 60 + "\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.server_close()


if __name__ == "__main__":
    main()
