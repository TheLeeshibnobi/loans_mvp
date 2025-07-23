import bcrypt
from supabase import create_client, Client
from flask import session
import os
import random
import string


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

    def sign_up(self, name, email, password, secret_key):
        try:
            # 1. Check if email already exists
            existing = self.supabase.table("users").select("email").eq("email", email).execute()
            if existing.data:
                return {"success": False, "message": "Email already registered."}

            # 2. Check both tables for the key
            key_response = self.supabase.table("secret_keys").select("id", "key").eq("key", secret_key).execute()
            admin_key_response = self.supabase.table("admin_keys").select("id", "key", "business_id").eq("key",
                                                                                                         secret_key).execute()

            if not key_response.data and not admin_key_response.data:
                return {"success": False, "message": "Invalid registration secret key."}

            # 3. Determine role and optional business_id
            if admin_key_response.data:
                role = "admin"
                key_table = "admin_keys"
                key_id = admin_key_response.data[0]["id"]
                business_id = admin_key_response.data[0]["business_id"]
            else:
                role = "viewer"
                key_table = "secret_keys"
                key_id = key_response.data[0]["id"]
                business_id = key_response.data[0]["business_id"]

            # 4. Hash the password securely
            hashed_password = self.hash_password(password)

            # 5. Prepare user data
            data = {
                "name": name.strip(),
                "email": email.strip().lower(),
                "role": role,
                "password": hashed_password
            }

            # Include business_id if it's from admin_keys
            if business_id:
                data["business_id"] = business_id

            # 6. Insert the new user
            result = self.supabase.table("users").insert(data).execute()

            if result.data:
                # 7. Delete the key if it's from secret_keys (one-time use)
                if key_table == "secret_keys":
                    self.supabase.table("secret_keys").delete().eq("id", key_id).execute()

                return {"success": True, "message": "User created successfully."}
            else:
                return {"success": False, "message": "Signup failed due to a database error."}

        except Exception as e:
            return {"success": False, "message": f"Signup failed: {str(e)}"}

    def login(self, email, password):
        try:
            result = self.supabase.table("users").select("*").eq("email", email).execute()

            if not result.data or len(result.data) == 0:
                return {"success": False, "message": "User not found."}

            user = result.data[0]

            if self.verify_password(password, user["password"]):
                # Store user in session here
                session["user"] = {
                    "id": user["id"],
                    "name": user["name"],
                    "email": user["email"],
                    "role": user["role"]
                }
                return {"success": True, "message": "Login successful", "role": user["role"]}
            else:
                return {"success": False, "message": "Invalid password."}

        except Exception as e:
            return {"success": False, "message": f"Login failed: {str(e)}"}

    def business_login(self, business_email, business_password):
        """Logs the user into the business"""
        try:
            # Get business user by email
            result = self.supabase.table("business_users").select("*").eq("email", business_email).execute()

            # Check if user exists
            if not result.data:
                return {"success": False, "message": "Invalid email or password"}

            business_user = result.data[0]

            # Verify password (assuming passwords are hashed)
            stored_password = business_user.get("password")

            # If passwords are hashed, use proper verification:
            # if not bcrypt.checkpw(business_password.encode('utf-8'), stored_password.encode('utf-8')):
            #     return {"success": False, "message": "Invalid email or password"}

            # If passwords are stored in plain text (NOT recommended for production):
            if stored_password != business_password:
                return {"success": False, "message": "Invalid email or password"}

            # Return success with business data
            return {
                "success": True,
                "message": "Business login successful",
                "business_data": {
                    "id": business_user.get("id"),
                    "email": business_user.get("email"),
                    "name": business_user.get("business_name"),  # Adjust field name as needed
                    # Add other relevant business fields
                }
            }

        except Exception as e:
            return {"success": False, "message": f"Login failed: {str(e)}"}

    def business_signup(self, business_name, email, password):
        """Signs up a new business to the database"""

        data = {
            'business_name': business_name,
            'email': email,
            'password': password
        }

        try:
            result = self.supabase.table('business_users').insert(data).execute()
            if result.data:
                print(f'{business_name} has been signed up')

                # store admin key for that business
                admin_key = self.create_admin_key()
                business_id = result.data[0]['id']

                admin_key_data = {
                    'key': admin_key,
                    'business_id': business_id
                }

                key_response = self.supabase.table('admin_keys').insert(admin_key_data).execute()

                if key_response.data:
                    return key_response.data[0]['key']
                else:
                    print('Error inserting admin key')
                    return None
            else:
                print(f'Error signing up {business_name}')
                return None

        except Exception as e:
            print(f'Exception: {e}')
            return None

    def create_admin_key(self):
        """Creates and returns a random 6-character admin key"""
        characters = string.ascii_letters + string.digits  # a-zA-Z0-9
        admin_key = ''.join(random.choices(characters, k=6))
        return admin_key



