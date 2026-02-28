from google import genai
import os
import json
import time
from dao import db


class ContentEngine:
    def __init__(self):
        self.api_key = os.getenv("GEMINI_API_KEY")
        self.mock_mode = False

        if not self.api_key:
            print("⚠️ WARNING: GEMINI_API_KEY not found. Switching to MOCK_MODE.")
            self.mock_mode = True
        else:
            try:
                self.client = genai.Client(api_key=self.api_key)
            except Exception as e:
                print(f"⚠️ API Error during config: {e}. Switching to MOCK_MODE.")
                self.mock_mode = True

    def _parse_profile(self, user_data):
        """Helper to ensure profile_data is a dict."""
        profile_meta = user_data.get("profile_data", {})
        if isinstance(profile_meta, str):
            try:
                profile_meta = json.loads(profile_meta)
            except json.JSONDecodeError:
                profile_meta = {}
        return {**profile_meta, **user_data}

    def validate_data(self, required_keys, user_profile):
        """
        Ensures the user has all necessary fields.
        """
        if not required_keys:
            return True, []

        full_profile = self._parse_profile(user_profile)
        missing = [key for key in required_keys if key not in full_profile]

        return len(missing) == 0, missing

    def generate_message(self, template_name, user_data, context_override=""):
        """
        Generates the message. Uses AI if available, else Mock.
        """
        # 1. Fetch Template
        template_record = db.get_template(template_name)
        if not template_record:
            return {
                "status": "error",
                "error": f"Template '{template_name}' not found.",
            }

        # 2. Validate
        is_valid, missing = self.validate_data(
            template_record.get("required_keys"), user_data
        )
        if not is_valid:
            return {"status": "failed", "error": f"Missing required data: {missing}"}

        # Prepare data for generation (Common for both modes)
        full_profile = self._parse_profile(user_data)

        # 3. MOCK MODE (Fallback)
        if self.mock_mode:
            print(
                f"[MOCK] Generating email for {user_data.get('email')} using template '{template_name}'..."
            )
            time.sleep(1)  # Simulate API latency

            base_content = template_record["content"]
            mock_content = base_content

            # Very basic variable injection for the mock
            for k, v in full_profile.items():
                # Handle {{key}} - simple string replace
                placeholder = "{{" + str(k) + "}}"
                if placeholder in mock_content:
                    mock_content = mock_content.replace(placeholder, str(v))

            return {
                "status": "success",
                "content": f"[MOCK GENERATION] \n{mock_content}\n[END MOCK]",
                "template_id": template_record["id"],
            }

        # 4. REAL AI GENERATION
        try:
            prompt = f"""
            TASK: Fill this email template.
            TEMPLATE: "{template_record["content"]}"
            DATA: {json.dumps(full_profile, default=str)}
            CONTEXT: {context_override}
            OUTPUT: Final email text only.
            """

            # Attempt generation
            response = self.client.models.generate_content(
                model="gemma-3-27b-it",
                contents=prompt,
            )

            # Check if response was blocked
            if not response.text:
                return {"status": "error", "error": "AI response was blocked or empty."}

            return {
                "status": "success",
                "content": response.text.strip(),
                "template_id": template_record["id"],
            }
        except Exception as e:
            # Fallback to Mock if API fails at runtime?
            # For now, return error to be explicit
            return {"status": "error", "error": str(e)}


engine = ContentEngine()
