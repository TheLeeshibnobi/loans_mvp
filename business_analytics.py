from supabase import create_client, Client
import datetime
import os
from calendar import monthrange
from collections import Counter, defaultdict

import plotly.express as px
import plotly.graph_objects as go
import pandas as pd


class BusinessAnalytics:
    def __init__(self):
        url = os.getenv("SUPABASE_URL")
        service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

        if not url or not service_role_key:
            raise ValueError("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY is not set.")

        try:
            self.supabase: Client = create_client(url, service_role_key)
        except Exception as e:
            raise ValueError(f"Failed to create Supabase client: {str(e)}")

    # Define consistent color scheme matching your white/blue theme
    def get_color_palette(self):
        return {
            'primary': '#6b48ff',      # Your main purple/blue
            'secondary': '#4169E1',    # Royal blue
            'accent': '#87CEEB',       # Sky blue
            'light': '#E6F3FF',        # Very light blue
            'success': '#28a745',      # Green for positive metrics
            'warning': '#ffc107',      # Yellow for warnings
            'info': '#17a2b8',         # Teal for info
            'gradient_start': '#6b48ff',
            'gradient_end': '#87CEEB'
        }

    def validate_year(self, year):
        if not isinstance(year, int):
            try:
                year = int(year)
            except (ValueError, TypeError):
                raise ValueError(f"Year must be a valid integer, got: {year}")
        return year

    def month_map(self, year: int):
        if not isinstance(year, int) or not (datetime.MINYEAR <= year <= datetime.MAXYEAR):
            raise ValueError(f"Year must be an integer between {datetime.MINYEAR} and {datetime.MAXYEAR}, got: {year}")

        try:
            month_ranges = {
                month: (
                    f"{year}-{str(i).zfill(2)}-01T00:00:00+00:00",
                    f"{year}-{str(i).zfill(2)}-{monthrange(year, i)[1]}T23:59:59+00:00"
                )
                for i, month in enumerate([
                    "January", "February", "March", "April", "May", "June",
                    "July", "August", "September", "October", "November", "December"
                ], start=1)
            }

            month_ranges["All Months"] = (
                f"{year}-01-01T00:00:00+00:00",
                f"{year}-12-31T23:59:59+00:00"
            )

            return month_ranges
        except Exception as e:
            raise ValueError(f"Error creating month map for year {year}: {str(e)}")

    def apply_gender_filter(self, query, gender):
        try:
            if gender == "All":
                return query.or_("gender.eq.Male,gender.eq.Female")
            return query.eq("gender", gender)
        except Exception as e:
            print(f"Error applying gender filter: {str(e)}")
            return query

    def get_borrower_ids(self, gender, business_id):
        try:
            query = self.supabase.table("borrowers").select("id")
            query = query.eq("business_id", business_id)
            query = self.apply_gender_filter(query, gender)
            response = query.execute()

            if not response or not response.data:
                return []

            return [b["id"] for b in response.data if b and "id" in b]
        except Exception as e:
            print(f"Error fetching borrower IDs: {str(e)}")
            return []

    def get_loans(self, borrower_ids, start, end, business_id, filters=None):
        try:
            if not borrower_ids:
                return []

            query = self.supabase.table("loans").select("*")
            query = query.eq("business_id", business_id)
            query = query.in_("borrower_id", borrower_ids)
            query = query.gte("created_at", start).lte("created_at", end)

            if filters:
                for key, value in filters.items():
                    try:
                        if isinstance(value, list):
                            query = query.in_(key, value)
                        else:
                            query = query.eq(key, value)
                    except Exception as filter_error:
                        print(f"Error applying filter {key}={value}: {str(filter_error)}")

            response = query.execute()
            return response.data if response and response.data else []
        except Exception as e:
            print(f"Error fetching loans: {str(e)}")
            return []

    def total_loans_issued(self, gender, month, year, business_id):
        try:
            year = self.validate_year(year)
            start, end = self.month_map(year)[month]
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return 0

            loans = self.get_loans(borrower_ids, start, end, business_id)
            return len(loans) if loans else 0
        except Exception as e:
            print(f"Error calculating total loans issued: {str(e)}")
            return 0

    def total_revenue_generated(self, gender, month, year, business_id):
        try:
            year = self.validate_year(year)
            start, end = self.month_map(year)[month]
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return 0

            # Step 1: Get loan IDs
            loans = self.get_loans(borrower_ids, start, end, business_id)
            if not loans:
                return 0

            loan_ids = [loan['id'] for loan in loans if loan and 'id' in loan]
            if not loan_ids:
                return 0

            # Step 2: Get repayment amounts for those loans
            repayment_query = (
                self.supabase
                .table("repayments")
                .select("amount")
                .eq("business_id", business_id)
                .in_("loan_id", loan_ids)
            )
            repayment_response = repayment_query.execute()

            if not repayment_response or not repayment_response.data:
                return 0

            total = 0
            for item in repayment_response.data:
                if item and 'amount' in item and item['amount'] is not None:
                    try:
                        total += float(item['amount'])
                    except (ValueError, TypeError):
                        continue
            return total
        except Exception as e:
            print(f"Error calculating total revenue: {str(e)}")
            return 0

    def default_rate(self, gender, month, year, business_id):
        try:
            year = self.validate_year(year)
            start, end = self.month_map(year)[month]
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return "0%"

            loans = self.get_loans(borrower_ids, start, end, business_id)
            if not loans:
                return "0%"

            defaults = self.get_loans(
                borrower_ids, start, end, business_id,
                filters={"status": ["Default", "Overdue"]}
            )

            if not defaults:
                return "0%"

            default_rate = (len(defaults) / len(loans)) * 100
            return f"{round(default_rate, 2)}%"
        except Exception as e:
            print(f"Error calculating default rate: {str(e)}")
            return "0%"

    def active_portfolio(self, gender, month, year, business_id):
        try:
            year = self.validate_year(year)
            start, end = self.month_map(year)[month]
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return 0

            active_loans = self.get_loans(
                borrower_ids, start, end, business_id,
                filters={"status": "Active"}
            )

            if not active_loans:
                return 0

            total = 0
            for item in active_loans:
                if item and 'amount' in item and item['amount'] is not None:
                    try:
                        total += float(item['amount'])
                    except (ValueError, TypeError):
                        continue
            return total
        except Exception as e:
            print(f"Error calculating active portfolio: {str(e)}")
            return 0

    def loan_reason_trend_data(self, gender, year, loan_reason, business_id):
        """Returns the number of loans for a specific loan_reason across all months in a year"""
        try:
            year = self.validate_year(year)
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return {}

            monthly_data = {}

            # Loop through all 12 months
            for month in range(1, 13):
                month_name = [
                    'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                ][month - 1]

                try:
                    start, end = self.month_map(year)[month_name]
                    # Get all loans within that month
                    all_loans = self.get_loans(borrower_ids, start, end, business_id)

                    # Count loans for the specific reason
                    reason_count = 0
                    if all_loans:
                        for loan in all_loans:
                            if loan and loan.get('loan_reason') == loan_reason:
                                reason_count += 1

                    monthly_data[month_name] = reason_count
                except Exception as month_error:
                    print(f"Error processing month {month_name}: {str(month_error)}")
                    monthly_data[month_name] = 0

            return monthly_data
        except Exception as e:
            print(f"Error generating loan reason trend data: {str(e)}")
            return {}

    def interest_vs_transaction_costs_data(self, gender, year, business_id):
        """returns data of total_interest v.s total_transaction_costs for a certain period"""
        try:
            year = self.validate_year(year)
            borrower_ids = self.get_borrower_ids(gender, business_id)
            if not borrower_ids:
                return {}

            monthly_data = {}

            # Loop through all 12 months
            for month in range(1, 13):
                month_name = [
                    'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                ][month - 1]

                try:
                    start, end = self.month_map(year)[month_name]
                    # Get all loans within that month
                    all_loans = self.get_loans(borrower_ids, start, end, business_id)

                    # Calculate total interest and transaction costs for the month
                    total_interest = 0
                    total_transaction_costs = 0

                    if all_loans:
                        for loan in all_loans:
                            if not loan:
                                continue

                            # Handle None values by defaulting to 0
                            try:
                                amount = float(loan.get('amount') or 0)
                                interest_rate = float(loan.get('interest_rate') or 0)
                                transaction_cost = float(loan.get('transaction_costs') or 0)

                                # Calculate interest earned for this loan
                                interest_earned = (amount * interest_rate) / 100

                                total_interest += interest_earned
                                total_transaction_costs += transaction_cost
                            except (ValueError, TypeError) as calc_error:
                                print(f"Error calculating values for loan: {str(calc_error)}")
                                continue

                    monthly_data[month_name] = {
                        'total_interest': round(total_interest, 2),
                        'total_transaction_costs': round(total_transaction_costs, 2)
                    }

                except Exception as month_error:
                    print(f"Error processing month {month_name}: {str(month_error)}")
                    monthly_data[month_name] = {
                        'total_interest': 0,
                        'total_transaction_costs': 0
                    }

            return monthly_data
        except Exception as e:
            print(f"Error generating interest vs transaction costs data: {str(e)}")
            return {}

    def loan_repayments_vs_expenses(self, gender, year, business_id):
        """Returns data of total_repaid_loans vs total_expenses (including discounts) for a certain period"""
        try:
            print(f"DEBUG: Starting with gender={gender}, year={year}, business_id={business_id}")

            year = self.validate_year(year)
            print(f"DEBUG: Validated year: {year}")

            # Fix gender filter - handle 'All Genders' vs 'All'
            filter_gender = 'All' if gender == 'All Genders' else gender
            borrower_ids = self.get_borrower_ids(filter_gender, business_id)
            print(f"DEBUG: Found borrower_ids: {borrower_ids}")

            if not borrower_ids:
                print("DEBUG: No borrower IDs found - returning empty dict")
                return {}

            # Get ALL loan IDs for these borrowers (not time-limited)
            all_loans_response = self.supabase.table('loans') \
                .select('id') \
                .eq('business_id', business_id) \
                .in_('borrower_id', borrower_ids) \
                .execute()

            all_loan_ids = [loan['id'] for loan in all_loans_response.data if loan and 'id' in loan]
            print(f"DEBUG: Total loan IDs for borrowers: {len(all_loan_ids)}")

            if not all_loan_ids:
                print("DEBUG: No loan IDs found for borrowers")
                return {}

            monthly_data = {}

            for month in range(1, 13):
                month_name = [
                    'January', 'February', 'March', 'April', 'May', 'June',
                    'July', 'August', 'September', 'October', 'November', 'December'
                ][month - 1]

                try:
                    start, end = self.month_map(year)[month_name]
                    print(f"DEBUG: Processing {month_name} - Date range: {start} to {end}")

                    # Get repayments MADE during this month (using created_at)
                    repayments_response = self.supabase.table('repayments') \
                        .select('amount, discount, created_at, loan_id') \
                        .eq('business_id', business_id) \
                        .in_('loan_id', all_loan_ids) \
                        .gte('created_at', start) \
                        .lte('created_at', end) \
                        .execute()

                    print(f"DEBUG: Repayments response for {month_name}: {repayments_response}")
                    print(f"DEBUG: Repayments data for {month_name}: {repayments_response.data}")

                    total_repaid = 0
                    total_discount = 0

                    if repayments_response and repayments_response.data:
                        for row in repayments_response.data:
                            if not row:
                                continue
                            try:
                                amount = float(row.get('amount') or 0)
                                discount = float(row.get('discount') or 0)
                                total_repaid += amount
                                total_discount += discount
                                print(f"DEBUG: Processing repayment - amount: {amount}, discount: {discount}")
                            except (ValueError, TypeError) as calc_error:
                                print(f"Error calculating repayment values: {str(calc_error)}")
                                continue
                    else:
                        print(f"DEBUG: No repayments found for {month_name}")

                    # Get expense data from the expenses table for the same period (using created_at)
                    print(f"DEBUG: Querying expenses for date range: {start} to {end}")

                    expenses_response = self.supabase.table('expenses') \
                        .select('amount, created_at') \
                        .eq('business_id', business_id) \
                        .gte('created_at', start) \
                        .lte('created_at', end) \
                        .execute()

                    print(f"DEBUG: Expenses response for {month_name}: {expenses_response}")
                    print(f"DEBUG: Expenses data for {month_name}: {expenses_response.data}")

                    total_expense = 0
                    if expenses_response and expenses_response.data:
                        for row in expenses_response.data:
                            try:
                                expense_amount = float(row.get('amount') or 0)
                                total_expense += expense_amount
                                print(f"DEBUG: Processing expense - amount: {expense_amount}")
                            except (ValueError, TypeError) as expense_error:
                                print(f"DEBUG: Error processing expense: {expense_error}")
                                continue
                    else:
                        print(f"DEBUG: No expenses found for {month_name}")

                    # Include the discount as an expense
                    total_expenses_combined = total_expense + total_discount

                    print(f"DEBUG: {month_name} totals - repaid: {total_repaid}, expenses: {total_expenses_combined}")

                    monthly_data[month_name] = {
                        'total_repaid': float(total_repaid),
                        'total_expenses': float(total_expenses_combined)
                    }

                except Exception as month_error:
                    print(f"Error processing {month_name}: {str(month_error)}")
                    import traceback
                    traceback.print_exc()
                    monthly_data[month_name] = {
                        'total_repaid': 0,
                        'total_expenses': 0
                    }

            print(f"DEBUG: Final monthly_data: {monthly_data}")
            return monthly_data

        except Exception as e:
            print(f"Error generating loan repayments vs expense data: {str(e)}")
            import traceback
            traceback.print_exc()
            return {}

    def loan_reason_trend_chart(self, gender, year, loan_reason, business_id):
        """Returns an HTML string of a smooth area chart showing trend for a specific loan reason"""
        try:
            trend_data = self.loan_reason_trend_data(gender, year, loan_reason, business_id)
            colors = self.get_color_palette()

            if not trend_data:
                return "<div class='text-center py-4 text-muted'>No loan data available for the specified filters.</div>"

            months = list(trend_data.keys())
            counts = list(trend_data.values())

            if not months or not counts:
                return "<div class='text-center py-4 text-muted'>No data available to generate chart.</div>"

            # Create area chart with gradient fill
            fig = go.Figure()

            # Add area trace
            fig.add_trace(go.Scatter(
                x=months,
                y=counts,
                mode='lines+markers',
                fill='tonexty',
                fillcolor=f'rgba(107, 72, 255, 0.1)',  # Light fill
                line=dict(color=colors['primary'], width=3, shape='spline', smoothing=1.3),
                marker=dict(
                    size=8,
                    color=colors['primary'],
                    symbol='circle',
                    line=dict(width=2, color='white')
                ),
                name=f'{loan_reason}',
                hovertemplate='<b>%{x}</b><br>Loans: %{y}<br><extra></extra>',
                showlegend=False
            ))

            # Add a baseline at y=0 for the fill
            fig.add_trace(go.Scatter(
                x=months,
                y=[0] * len(months),
                mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                showlegend=False,
                hoverinfo='skip'
            ))

            # Update layout for mobile-friendly design
            fig.update_layout(
                title={
                    'text': f'Loan Trend: {loan_reason}<br><span style="font-size:12px; color:#666;">{gender.title()} - {year}</span>',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 14, 'family': 'Arial, sans-serif', 'color': '#333'}
                },
                xaxis_title='',
                yaxis_title='Number of Loans',
                font=dict(size=11, color='#666'),
                margin=dict(l=50, r=20, t=80, b=60),
                height=350,  # Fixed height for consistency
                xaxis=dict(
                    tickangle=0,
                    tickfont=dict(size=10),
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)',
                    gridwidth=1
                ),
                yaxis=dict(
                    tickfont=dict(size=10),
                    rangemode='tozero',
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)',
                    gridwidth=1
                ),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=False
            )

            return fig.to_html(include_plotlyjs='cdn', full_html=False, config={
                'responsive': True,
                'displayModeBar': False,
                'scrollZoom': False
            })
        except Exception as e:
            error_msg = f"Error generating chart: {str(e)}"
            print(error_msg)
            return f"<div class='text-center py-4 text-danger'>{error_msg}</div>"

    def interest_vs_transaction_costs_chart(self, gender, year, business_id):
        """Returns an HTML string of a mobile-friendly stacked area chart"""
        try:
            chart_data = self.interest_vs_transaction_costs_data(gender, year, business_id)
            colors = self.get_color_palette()

            if not chart_data:
                return "<div class='text-center py-4 text-muted'>No financial data available for the specified filters.</div>"

            months = list(chart_data.keys())
            interest_values = [chart_data[month]['total_interest'] for month in months]
            transaction_costs = [chart_data[month]['total_transaction_costs'] for month in months]

            if not months or len(interest_values) == 0 or len(transaction_costs) == 0:
                return "<div class='text-center py-4 text-muted'>Insufficient data available to generate chart.</div>"

            # Create stacked area chart
            fig = go.Figure()

            # Add transaction costs (bottom layer)
            fig.add_trace(go.Scatter(
                x=months,
                y=transaction_costs,
                mode='lines',
                fill='tonexty',
                fillcolor='rgba(255, 99, 132, 0.3)',
                line=dict(color='#ff6384', width=2),
                name='Transaction Costs',
                hovertemplate='<b>%{x}</b><br>Transaction Costs: $%{y:,.2f}<extra></extra>'
            ))

            # Add interest earned (top layer)
            fig.add_trace(go.Scatter(
                x=months,
                y=[i + t for i, t in zip(interest_values, transaction_costs)],
                mode='lines',
                fill='tonexty',
                fillcolor=f'rgba(107, 72, 255, 0.3)',
                line=dict(color=colors['primary'], width=2),
                name='Interest Earned',
                hovertemplate='<b>%{x}</b><br>Interest Earned: $%{customdata:,.2f}<extra></extra>',
                customdata=interest_values
            ))

            # Add baseline
            fig.add_trace(go.Scatter(
                x=months,
                y=[0] * len(months),
                mode='lines',
                line=dict(color='rgba(0,0,0,0)'),
                showlegend=False,
                hoverinfo='skip'
            ))

            fig.update_layout(
                title={
                    'text': f'Revenue Overview<br><span style="font-size:12px; color:#666;">{gender.title()} - {year}</span>',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 14, 'family': 'Arial, sans-serif', 'color': '#333'}
                },
                xaxis_title='',
                yaxis_title='Amount ($)',
                font=dict(size=11, color='#666'),
                margin=dict(l=60, r=20, t=80, b=60),
                height=350,
                xaxis=dict(
                    tickangle=0,
                    tickfont=dict(size=10),
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)'
                ),
                yaxis=dict(
                    tickfont=dict(size=10),
                    rangemode='tozero',
                    tickformat='$,.0f',
                    showgrid=True,
                    gridcolor='rgba(0,0,0,0.1)'
                ),
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.1,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=10)
                )
            )

            return fig.to_html(include_plotlyjs='cdn', full_html=False, config={
                'responsive': True,
                'displayModeBar': False,
                'scrollZoom': False
            })
        except Exception as e:
            error_msg = f"Error generating chart: {str(e)}"
            print(error_msg)
            return f"<div class='text-center py-4 text-danger'>{error_msg}</div>"

    def loan_repayments_vs_expenses_chart(self, gender, year, business_id):
        """Returns an HTML string of a mobile-friendly donut/pie chart comparing repayments and expenses"""
        try:
            chart_data = self.loan_repayments_vs_expenses(gender, year, business_id)
            colors = self.get_color_palette()

            if not chart_data:
                return "<div class='text-center py-4 text-muted'>No repayment data available for the specified filters.</div>"

            # Calculate yearly totals
            total_repaid = sum(chart_data[month]['total_repaid'] for month in chart_data)
            total_expenses = sum(chart_data[month]['total_expenses'] for month in chart_data)

            if total_repaid == 0 and total_expenses == 0:
                return "<div class='text-center py-4 text-muted'>No repayment or expense activity for this period.</div>"

            # Create donut chart
            fig = go.Figure(data=[go.Pie(
                labels=['Total Repaid', 'Total Expenses'],
                values=[total_repaid, total_expenses],
                hole=0.4,
                marker=dict(
                    colors=[colors['primary'], colors['accent']],
                    line=dict(color='white', width=2)
                ),
                textinfo='label+percent+value',
                texttemplate='<b>%{label}</b><br>%{percent}<br>$%{value:,.0f}',
                textfont=dict(size=11),
                hovertemplate='<b>%{label}</b><br>Amount: $%{value:,.2f}<br>Percentage: %{percent}<extra></extra>'
            )])

            # Add center text
            fig.add_annotation(
                text=f"<b>Total Activity</b><br>${(total_repaid + total_expenses):,.0f}",
                x=0.5, y=0.5,
                font=dict(size=12, color='#333'),
                showarrow=False
            )

            fig.update_layout(
                title={
                    'text': f'Repayments vs Expenses<br><span style="font-size:12px; color:#666;">{gender.title()} - {year}</span>',
                    'x': 0.5,
                    'xanchor': 'center',
                    'font': {'size': 14, 'family': 'Arial, sans-serif', 'color': '#333'}
                },
                font=dict(size=11, color='#666'),
                margin=dict(l=20, r=20, t=80, b=60),
                height=350,
                plot_bgcolor='rgba(0,0,0,0)',
                paper_bgcolor='rgba(0,0,0,0)',
                showlegend=True,
                legend=dict(
                    orientation="h",
                    yanchor="top",
                    y=-0.05,
                    xanchor="center",
                    x=0.5,
                    font=dict(size=10)
                )
            )

            return fig.to_html(include_plotlyjs='cdn', full_html=False, config={
                'responsive': True,
                'displayModeBar': False,
                'scrollZoom': False
            })
        except Exception as e:
            error_msg = f"Error generating chart: {str(e)}"
            print(error_msg)
            return f"<div class='text-center py-4 text-danger'>{error_msg}</div>"

