import bcrypt
from supabase import create_client, Client
from flask import session
import os


class UserAuthentication:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

    def hash_password(self, password: str) -> str:
        return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    def verify_password(self, password: str, hashed: str) -> bool:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))

    def sign_up(self, name, email, role, password, secret_key):
        try:
            # Check if email already exists
            existing = self.supabase.table("users").select("email").eq("email", email).execute()
            if existing.data:
                return {"success": False, "message": "Email already registered."}

            # Check if the provided secret key exists
            key_response = self.supabase.table("secret_keys").select("id", "key").eq("key", secret_key).execute()

            # Handle empty table or no matching key
            if not key_response.data or len(key_response.data) == 0:
                return {"success": False, "message": "Invalid registration secret key."}

            key_id = key_response.data[0]["id"]  # Safe to access now

            # Hash the password securely
            hashed_password = self.hash_password(password)

            # Prepare user data
            data = {
                "name": name.strip(),
                "email": email.strip().lower(),
                "role": role.strip().lower(),
                "password": hashed_password
            }

            # Insert the new user
            result = self.supabase.table("users").insert(data).execute()

            if result.data:
                # Delete the used secret key
                delete_result = self.supabase.table("secret_keys").delete().eq("id", key_id).execute()
                return {"success": True, "message": "User created successfully."}
            else:
                return {"success": False, "message": "Signup failed due to a database error."}

        except Exception as e:
            return {"success": False, "message": f"Signup failed: {str(e)}"}

    def login(self, email, password):
        try:
            result = self.supabase.table("users").select("*").eq("email", email).execute()

            # Handle empty table or no matching user
            if not result.data or len(result.data) == 0:
                return {"success": False, "message": "User not found."}

            user = result.data[0]  # Safe to access now

            if self.verify_password(password, user["password"]):
                session["user"] = {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"]
                }
                return {"success": True, "message": "Login successful."}
            else:
                return {"success": False, "message": "Invalid password."}

        except Exception as e:
            return {"success": False, "message": f"Login failed: {str(e)}"}