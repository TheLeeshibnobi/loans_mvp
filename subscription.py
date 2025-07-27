import os
import datetime
from supabase import create_client, Client
import requests
import time


class Subscriptions:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        self.supabase: Client = create_client(url, service_role_key)

        # TuMeNy API config
        self.tumeny_api_key = os.getenv("TUMENY_API_KEY")
        self.tumeny_api_secret = os.getenv("TUMENY_API_SECRET")
        if not self.tumeny_api_key or not self.tumeny_api_secret:
            raise Exception("Missing TUMENY_API_KEY or TUMENY_API_SECRET in environment variables.")

        # Generate auth token
        self.tumeny_token, self.token_expiry = self.get_tumeny_auth_token()
        print(f" TuMeNy token acquired: {self.tumeny_token[:10]}...")

        self.headers = {
            "Authorization": f"Bearer {self.tumeny_token}",
            "Content-Type": "application/json"
        }

        self.base_url = os.getenv('https://tumeny.herokuapp.com/api/token')

        # EXCHANGE RTE API
        self.exchange_rate_url = os.getenv('EXCHANGE_RATE_URL')


        # email configuration
        #self.email_password = os.getenv('EMAIL_KEY')

    def get_tumeny_auth_token(self):
        url = "https://tumeny.herokuapp.com/api/token"
        headers = {
            "apiKey": self.tumeny_api_key,
            "apiSecret": self.tumeny_api_secret
        }
        response = requests.post(url, headers=headers)
        if response.status_code == 200:
            data = response.json()
            return data['token'], data['expireAt']
        else:
            raise Exception(f"Failed to get TuMeNy token: {response.text}")

    def convert_to_zmw(self, amount):
        """Converts the USD amount to ZMW and returns the converted value"""
        response = requests.get(self.exchange_rate_url)
        data = response.json()

        # Make sure the API returned success and contains the rate
        rate = data.get("conversion_rate")
        if rate:
            return round(amount * rate, 2)
        else:
            raise ValueError("Failed to fetch exchange rate.")

    def request_payment(self, amount, first_name, last_name, email, phone, plan):
        """Requests a payment using TuMeNy API and returns the payment ID"""
        url = "https://tumeny.herokuapp.com/api/v1/payment"

        headers = {
            "Authorization": f"Bearer {self.tumeny_token}",
            "Content-Type": "application/json"
        }

        try:
            zmw_amount = self.convert_to_zmw(amount)

            payload = {
                "description": f"Inxource {plan} Plan Subscription",
                "customerFirstName": first_name,
                "customerLastName": last_name,
                "email": email,
                "phoneNumber": phone,
                "amount": zmw_amount
            }

            response = requests.post(url, json=payload, headers=headers, timeout=30)
            response_data = response.json()

            if response.status_code == 200 and 'payment' in response_data:
                payment_id = response_data['payment']['id']
                return {'success': True, 'payment_id': payment_id}
            else:
                return {'success': False, 'message': 'Invalid response from payment API'}

        except requests.exceptions.Timeout:
            return {'success': False, 'message': 'Payment request timed out.'}
        except requests.exceptions.RequestException as e:
            print(f'Payment request exception: {e}')
            return {'success': False, 'message': 'Payment service unavailable.'}
        except Exception as e:
            print(f'Unexpected error: {e}')
            return {'success': False, 'message': 'Unexpected error occurred.'}


    def check_business_pay_status(self, business_id):
        """checks if the business has a paid subscription or not"""
        try:
            response = self.supabase.table('business_users').select('paid').eq('id', business_id).execute()
            return response.data[0]['paid']
        except Exception as e:
            print(f'Exception: {e}')


    def check_payment_status_with_retries(self, payment_id, max_attempts=5, delay_seconds=10):
        """
        Polls the TuMeNy API to check payment status every `delay_seconds` up to `max_attempts`.
        Returns True if payment succeeded, False otherwise.
        """
        url = f"https://tumeny.herokuapp.com/api/v1/payment/{payment_id}"
        headers = {
            "Authorization": f"Bearer {self.tumeny_token}"
        }

        for attempt in range(max_attempts):
            try:
                response = requests.get(url, headers=headers, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    status = data['payment']['status'].lower()
                    print(f"[Attempt {attempt + 1}] Payment status: {status}")

                    if status == "success":
                        return True
                    elif status == "failed":
                        return False

                else:
                    print(f"Unexpected status code: {response.status_code}")
            except Exception as e:
                print(f"Error checking payment status: {e}")

            print(f"Waiting {delay_seconds} seconds before next attempt...")
            time.sleep(delay_seconds)

        return False  # After all attempts, still not successful

    def buy_plan(self,business_id,  amount, first_name, last_name, email, phone, plan):
        """Handles the buying of a selected plan and updates payment status in a database"""

        try:
            # Step 1: Request payment
            result = self.request_payment(amount, first_name, last_name, email, phone, plan)

            if not result.get("success"):
                print("Failed to initiate payment:", result.get("message"))
                return False

            # Step 2: Extract payment ID and check payment status
            payment_id = result.get("payment_id")
            if not payment_id:
                print("No payment ID returned from payment request.")
                return False

            is_paid = self.check_payment_status_with_retries(payment_id)
            if not is_paid:
                print("Payment was not completed or failed.")
                return False

            # Step 3: Update the database
            try:
                update_response = self.supabase.table('business_users') \
                    .update({'paid': True}) \
                    .eq('id', business_id) \
                    .execute()

                if update_response.data:
                    return True
                else:
                    print("Failed to update 'paid' status in database.")
                    return False
            except Exception as db_error:
                print("Database update error:", db_error)
                return False

        except Exception as e:
            print("Unexpected error during plan purchase:", e)
            return False



