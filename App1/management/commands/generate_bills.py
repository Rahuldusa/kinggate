from django.core.management.base import BaseCommand
from django.core.mail import EmailMultiAlternatives
from django.utils.html import strip_tags
from django.conf import settings
from django.db.models import Q
from datetime import datetime, timedelta, date
from decimal import Decimal
import calendar
from io import BytesIO
import os
from App1.models import (
    Customer, BillingRecord, SubscriptionPlan, BillItem,
    CustomerLocation, Organization, data_logs, SubscriptionChange
)
from django.utils import timezone

# PDF Generation imports
try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.lib import colors
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
    from reportlab.pdfgen import canvas
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False


class Command(BaseCommand):
    help = 'Generate billing records for customers and their locations with PDF invoices and subscription change tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Run without creating records or sending emails',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)

        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No records will be created'))
        else:
            self.stdout.write(self.style.SUCCESS('LIVE MODE - Records will be created and emails sent'))

        if not PDF_AVAILABLE:
            self.stdout.write(self.style.ERROR('ReportLab not installed. Install with: pip install reportlab'))
            return

        try:
            self.organization = Organization.objects.first()
            if not self.organization:
                self.stdout.write(self.style.ERROR('No Organization record found. Please create one first.'))
                return
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error fetching Organization: {str(e)}'))
            return

        today = datetime.now().date()
        billing_date = today

        customers_processed = self.process_customers(billing_date, dry_run)
        customer_locations_processed = self.process_customer_locations(billing_date, dry_run)

        self.stdout.write(
            self.style.SUCCESS(
                f'\n{"="*60}\n'
                f'Billing generation complete!\n'
                f'{"="*60}\n'
                f'Customers processed: {customers_processed}\n'
                f'Customer Locations processed: {customer_locations_processed}\n'
                f'{"="*60}'
            )
        )

    # ─────────────────────────────────────────────────────────────
    # SUBSCRIPTION CHANGE HELPERS
    # ─────────────────────────────────────────────────────────────

    def get_subscription_changes_in_period(self, entity, location, period_start, period_end):
        filters = {
            'customer': entity,
            'change_date__gte': period_start,
            'change_date__lte': period_end,
        }
        if location:
            filters['customer_location'] = location
        else:
            filters['customer_location__isnull'] = True
        return list(SubscriptionChange.objects.filter(**filters).order_by('change_date'))

    def split_period_by_changes(self, period_start, period_end, subscription_changes, entity, location):
        periods = []
        current_start = period_start

        if location:
            current_plan = location.subscription_plan
            current_amount = location.custom_subscription_amount
        else:
            current_plan = entity.subscription_plan
            current_amount = entity.custom_subscription_amount

        if not subscription_changes:
            periods.append((period_start, period_end, current_plan, current_amount))
            return periods

        for change in subscription_changes:
            change_date = change.change_date
            if current_start < change_date:
                periods.append((
                    current_start,
                    change_date - timedelta(days=1),
                    change.old_subscription_plan,
                    change.old_custom_amount
                ))
            current_plan = change.new_subscription_plan
            current_amount = change.new_custom_amount
            current_start = change_date

        if current_start <= period_end:
            periods.append((current_start, period_end, current_plan, current_amount))

        return periods

    # ─────────────────────────────────────────────────────────────
    # AMOUNT CALCULATION
    # ─────────────────────────────────────────────────────────────

    def calculate_billing_amount_for_period(self, subscription_plan, custom_amount, period_start, period_end):
        if not subscription_plan:
            return Decimal('0.00')

        monthly_price = Decimal(str(custom_amount)) if custom_amount else Decimal(str(subscription_plan.price))

        days_in_month = calendar.monthrange(period_start.year, period_start.month)[1]
        billing_days = (period_end - period_start).days + 1

        if billing_days < days_in_month:
            daily_rate = monthly_price / Decimal(days_in_month)
            return (daily_rate * Decimal(billing_days)).quantize(Decimal('0.01'))

        return monthly_price

    def create_bill_items_for_billing_record(self, billing_record, sub_periods, gst_details):
        item_number = 1
        for period_start, period_end, subscription_plan, custom_amount in sub_periods:
            if not subscription_plan:
                continue
            base_amount = self.calculate_billing_amount_for_period(
                subscription_plan, custom_amount, period_start, period_end
            )
            days_count = (period_end - period_start).days + 1
            period_text = f"{period_start.strftime('%d-%m-%Y')} to {period_end.strftime('%d-%m-%Y')}"
            amount_text = (
                f"Custom: Rs {custom_amount}/month" if custom_amount
                else f"Rs {subscription_plan.price}/month"
            )
            description = f"Period: {period_text} ({days_count} days) | {amount_text}"

            BillItem.objects.create(
                billing_record=billing_record,
                item_name=subscription_plan.name,
                description=description,
                quantity=Decimal('1.00'),
                unit_price=base_amount,
                tax_percentage=Decimal('0.00')
            )
            item_number += 1

        self.stdout.write(self.style.SUCCESS(
            f'     Created {item_number - 1} bill item(s) for this invoice'
        ))

    # ─────────────────────────────────────────────────────────────
    # ADVANCE ADJUSTMENT  (does NOT auto-approve)
    # ─────────────────────────────────────────────────────────────

    def adjust_advance_amount(self, customer, bill_amount):
        """
        Deduct advance from customer balance and return adjustment details.
        NOTE: Does NOT mark anything as paid/approved — that requires manual approval.
        """
        customer.refresh_from_db()

        bill_amount = Decimal(str(bill_amount))
        advance_amount = Decimal(str(customer.advance_amount or 0))

        if advance_amount <= 0:
            return {
                'original_amount': bill_amount,
                'advance_used': Decimal('0.00'),
                'final_amount': bill_amount,
                'remaining_advance': Decimal('0.00'),
                'paid_amount': Decimal('0.00'),
                'balance_amount': bill_amount,
            }

        advance_used = min(advance_amount, bill_amount)
        final_amount = bill_amount - advance_used
        remaining_advance = advance_amount - advance_used

        # Deduct from customer advance — the bill itself still needs approval
        customer.advance_amount = remaining_advance
        customer.save(update_fields=['advance_amount'])
        customer.refresh_from_db()

        return {
            'original_amount': bill_amount,
            'advance_used': advance_used,
            'final_amount': final_amount,
            'remaining_advance': remaining_advance,
            'paid_amount': advance_used,      # amount deducted from advance
            'balance_amount': final_amount,   # remaining after advance
        }

    # ─────────────────────────────────────────────────────────────
    # COMPANY / GST HELPERS
    # ─────────────────────────────────────────────────────────────

    def get_company_for_entity(self, entity, location=None):
        if location and hasattr(location, 'customer'):
            return getattr(location.customer, 'company', None)
        elif hasattr(entity, 'company'):
            return getattr(entity, 'company', None)
        return None

    def get_gst_details(self, company, entity, location=None):
        """
        Returns GST details dict.
        KEY FIX: if company.gst_registered is False, GST is skipped entirely
        (gst_applicable = False) and billing is flat amount only.
        """
        # ── Is GST even applicable? ──────────────────────────────
        gst_applicable = bool(company and getattr(company, 'gst_registered', False))

        if not gst_applicable:
            return {
                'gst_applicable': False,
                'is_same_state': False,
                'state': '',
                'org_state': '',
                'gst_type': 'NO GST',
            }

        # ── Determine states ─────────────────────────────────────
        if location:
            state = getattr(location, 'state', None) or getattr(location, 'location_state', None)
        else:
            state = getattr(entity, 'state', None)

        org_state = getattr(company, 'state', None) or getattr(self.organization, 'state', None)

        def _state_name(s):
            if not s:
                return ''
            for attr in ('name', 'state_name'):
                if hasattr(s, attr):
                    return str(getattr(s, attr)).upper().strip()
            return str(s).upper().strip()

        state_name = _state_name(state)
        org_state_name = _state_name(org_state) or 'DELHI'
        is_same_state = (state_name == org_state_name)

        return {
            'gst_applicable': True,
            'is_same_state': is_same_state,
            'state': state_name,
            'org_state': org_state_name,
            'gst_type': 'INTRA-STATE' if is_same_state else 'INTER-STATE',
        }

    def calculate_gst(self, base_amount, gst_details):
        """
        KEY FIX: If gst_applicable is False, return flat amounts with zero GST.
        Otherwise compute CGST+SGST (same state) or IGST (inter-state).
        """
        base_amount = Decimal(str(base_amount))

        if not gst_details.get('gst_applicable', True):
            # No GST — flat amount only
            return {
                'base_amount': base_amount,
                'cgst': Decimal('0.00'),
                'sgst': Decimal('0.00'),
                'igst': Decimal('0.00'),
                'total_gst': Decimal('0.00'),
                'total_amount': base_amount,
            }

        if gst_details['is_same_state']:
            cgst = (base_amount * Decimal('0.09')).quantize(Decimal('0.01'))
            sgst = (base_amount * Decimal('0.09')).quantize(Decimal('0.01'))
            igst = Decimal('0.00')
            total_gst = cgst + sgst
        else:
            igst = (base_amount * Decimal('0.18')).quantize(Decimal('0.01'))
            cgst = Decimal('0.00')
            sgst = Decimal('0.00')
            total_gst = igst

        return {
            'base_amount': base_amount,
            'cgst': cgst,
            'sgst': sgst,
            'igst': igst,
            'total_gst': total_gst,
            'total_amount': base_amount + total_gst,
        }

    def get_monthly_periods(self, start_date, end_date):
        periods = []
        current_start = start_date
        while current_start <= end_date:
            last_day = calendar.monthrange(current_start.year, current_start.month)[1]
            current_end = min(current_start.replace(day=last_day), end_date)
            periods.append((current_start, current_end))
            if current_end >= end_date:
                break
            current_start = current_end + timedelta(days=1)
        return periods

    def calculate_billing_period(self, start_date, billing_date, entity, location=None):
        filters = {'customer': entity}
        if location:
            filters['customer_location'] = location
        else:
            filters['customer_location__isnull'] = True

        latest_bill = BillingRecord.objects.filter(**filters).order_by('-billing_end_date').first()
        billing_start_date = (
            latest_bill.billing_end_date + timedelta(days=1) if latest_bill else start_date
        )
        billing_end_date = billing_date.replace(day=1) - timedelta(days=1)

        if billing_start_date > billing_end_date:
            return None, None
        return billing_start_date, billing_end_date

    # ─────────────────────────────────────────────────────────────
    # PROCESS CUSTOMERS
    # ─────────────────────────────────────────────────────────────

    def process_customers(self, billing_date, dry_run):
        processed = 0
        customers = Customer.objects.filter(
            subscription_plan__isnull=False,
            status__iexact='Active',
            start_date__isnull=False
        )
        self.stdout.write(self.style.SUCCESS(f'\n[CUSTOMERS] Found {customers.count()} active customers'))

        for customer in customers:
            self.stdout.write(f'\nProcessing Customer: {customer.name}')

            company = self.get_company_for_entity(customer)
            if not company:
                self.stdout.write(self.style.WARNING(' Skipping: No company associated'))
                continue

            billing_start_date, billing_end_date = self.calculate_billing_period(
                customer.start_date, billing_date, customer, location=None
            )
            if billing_start_date is None:
                self.stdout.write(self.style.WARNING(' No unbilled periods found - all caught up!'))
                continue

            monthly_periods = self.get_monthly_periods(billing_start_date, billing_end_date)
            self.stdout.write(self.style.SUCCESS(
                f' Found {len(monthly_periods)} monthly billing period(s): {billing_start_date} to {billing_end_date}'
            ))

            billing_records_data = []
            bills_created = 0
            bills_skipped = 0

            for period_start, period_end in monthly_periods:
                existing_bill = BillingRecord.objects.filter(
                    customer=customer,
                    billing_start_date=period_start,
                    billing_end_date=period_end,
                    customer_location__isnull=True
                ).first()
                if existing_bill:
                    self.stdout.write(self.style.WARNING(
                        f'   Bill already exists for period {period_start.strftime("%d-%m-%Y")} to '
                        f'{period_end.strftime("%d-%m-%Y")} - Bill ID: {existing_bill.id}'
                    ))
                    bills_skipped += 1
                    continue

                subscription_changes = self.get_subscription_changes_in_period(
                    customer, None, period_start, period_end
                )
                if subscription_changes:
                    self.stdout.write(self.style.WARNING(
                        f'   Found {len(subscription_changes)} subscription change(s) in this period'
                    ))

                sub_periods = self.split_period_by_changes(
                    period_start, period_end, subscription_changes, customer, None
                )

                total_base_amount = Decimal('0.00')
                for sp_start, sp_end, sp_plan, sp_amount in sub_periods:
                    period_amount = self.calculate_billing_amount_for_period(
                        sp_plan, sp_amount, sp_start, sp_end
                    )
                    total_base_amount += period_amount
                    days = (sp_end - sp_start).days + 1
                    plan_name = sp_plan.name if sp_plan else "None"
                    amount_used = sp_amount if sp_amount else (sp_plan.price if sp_plan else 0)
                    self.stdout.write(self.style.SUCCESS(
                        f'      {sp_start.strftime("%d-%m-%Y")} to {sp_end.strftime("%d-%m-%Y")} '
                        f'({days} days): {plan_name} @ Rs {amount_used}/month = Rs {period_amount:.2f}'
                    ))

                gst_details = self.get_gst_details(company, customer)
                amounts = self.calculate_gst(total_base_amount, gst_details)

                total_bill_amount = amounts['total_amount']

                # ── Advance adjustment ──────────────────────────
                if hasattr(customer, 'advance_amount'):
                    advance_adjustment = self.adjust_advance_amount(customer, total_bill_amount)
                    paid_amount = advance_adjustment['paid_amount']
                    balance_amount = advance_adjustment['balance_amount']
                    discount_amount = advance_adjustment['advance_used']
                else:
                    paid_amount = Decimal('0.00')
                    balance_amount = total_bill_amount
                    discount_amount = Decimal('0.00')
                    advance_adjustment = {
                        'original_amount': total_bill_amount,
                        'advance_used': Decimal('0.00'),
                        'final_amount': total_bill_amount,
                        'remaining_advance': Decimal('0.00'),
                        'paid_amount': Decimal('0.00'),
                        'balance_amount': total_bill_amount,
                    }

                due_date = billing_date + timedelta(days=15)

                if not dry_run:
                    # ── FIX 1: paid=False always — never auto-mark paid ──
                    billing_record = BillingRecord.objects.create(
                        customer=customer,
                        amount=total_bill_amount,
                        discount_amount=discount_amount,
                        gst_amount=amounts['total_gst'],
                        gst_type=gst_details['gst_type'],
                        paid_amount=paid_amount,
                        balance_amount=balance_amount,
                        billing_date=billing_date,
                        due_date=due_date,
                        billing_start_date=period_start,
                        billing_end_date=period_end,
                        paid=False,   # FIX 1: never auto-approve
                    )

                    self.create_bill_items_for_billing_record(billing_record, sub_periods, gst_details)

                    # ── FIX 2: status always Pending; payment_date always None ──
                    status = 'Pending'
                    payment_mode = 'Advance Adjustment' if discount_amount > 0 else None
                    payment_date = None   # FIX 2: no date until manually approved

                    # ── Build details text ──────────────────────
                    gst_note = (
                        f"GST Type: {gst_details['gst_type']}\n"
                        f"CGST (9%): {amounts['cgst']:.2f}\n"
                        f"SGST (9%): {amounts['sgst']:.2f}\n"
                        f"IGST (18%): {amounts['igst']:.2f}\n"
                        f"Total GST: {amounts['total_gst']:.2f}\n"
                        if gst_details.get('gst_applicable')
                        else "GST: Not Applicable (Company not GST registered)\n"
                    )

                    details_text = f"""=== BILL GENERATED ===

Customer: {customer.name}
Company: {company.name}
Invoice Number: IN-{billing_record.id}

Billing Period: {period_start.strftime('%d-%m-%Y')} to {period_end.strftime('%d-%m-%Y')}
Billing Date: {billing_date.strftime('%d-%m-%Y')}
Due Date: {due_date.strftime('%d-%m-%Y')}

"""
                    if subscription_changes:
                        details_text += "Subscription Changes:\n"
                        for change in subscription_changes:
                            old_plan = change.old_subscription_plan.name if change.old_subscription_plan else "None"
                            new_plan = change.new_subscription_plan.name if change.new_subscription_plan else "None"
                            details_text += f"  {change.change_date}: {old_plan} to {new_plan}\n"
                        details_text += "\n"

                    details_text += f"""Financial Summary:
Base Amount: {amounts['base_amount']:.2f}
{gst_note}Total Amount: {total_bill_amount:.2f}
Advance Adjusted: {paid_amount:.2f}
Balance Amount: {balance_amount:.2f}
Status: {status}
"""

                    # ── FIX 3: is_approved=False always ─────────
                    data_logs.objects.create(
                        user=None,
                        customer=customer,
                        location=None,
                        billing_record=billing_record,
                        payment_amount=paid_amount,
                        billing_period_start=period_start,
                        billing_period_end=period_end,
                        balance_amount=balance_amount,
                        status=status,
                        payment_mode=payment_mode,
                        payment_date=None,       # FIX 2
                        total_paid=paid_amount,
                        is_payment=False,
                        is_approved=False,       # FIX 3
                        action='Bill Generated',
                        details=details_text.strip()
                    )

                    amounts['subtotal'] = total_bill_amount
                    amounts['advance_used'] = discount_amount
                    amounts['total_amount'] = balance_amount
                    amounts['sub_periods'] = sub_periods

                    pdf_buffer = self.generate_invoice_pdf(
                        billing_record,
                        customer.subscription_plan,
                        customer,
                        company,
                        gst_details,
                        amounts,
                        location=None,
                        advance_adjustment=advance_adjustment,
                        sub_periods=sub_periods
                    )

                    billing_records_data.append({
                        'billing_record': billing_record,
                        'pdf_buffer': pdf_buffer,
                        'amounts': amounts,
                        'period_start': period_start,
                        'period_end': period_end
                    })

                    bills_created += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'   Bill #{billing_record.id} created - '
                        f'{period_start.strftime("%d-%m-%Y")} to {period_end.strftime("%d-%m-%Y")}, '
                        f'Total: Rs {total_bill_amount}, Advance: Rs {paid_amount}, Balance: Rs {balance_amount}'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'   [DRY RUN] Would generate bill - {period_start} to {period_end}, '
                        f'Total: Rs {amounts["total_amount"]}'
                    ))
                    bills_created += 1

            if bills_created > 0 or bills_skipped > 0:
                self.stdout.write(self.style.SUCCESS(
                    f' Summary: {bills_created} bill(s) created, {bills_skipped} skipped'
                ))

            if not dry_run and billing_records_data:
                self.send_consolidated_billing_email(
                    recipient_email=customer.email,
                    recipient_name=customer.name,
                    billing_records_data=billing_records_data,
                    subscription_plan=customer.subscription_plan,
                    entity_type='Customer',
                    entity=customer,
                    company=company,
                    gst_details=gst_details
                )
                processed += 1
            elif bills_created > 0 and dry_run:
                processed += 1

        return processed

    # ─────────────────────────────────────────────────────────────
    # PROCESS CUSTOMER LOCATIONS
    # ─────────────────────────────────────────────────────────────

    def process_customer_locations(self, billing_date, dry_run):
        processed = 0
        locations = CustomerLocation.objects.filter(
            subscription_plan__isnull=False,
            is_active=True,
            start_date__isnull=False,
            customer__status__iexact='Active'
        ).select_related('customer', 'subscription_plan')

        self.stdout.write(self.style.SUCCESS(f'\n[CUSTOMER LOCATIONS] Found {locations.count()} active locations'))

        for location in locations:
            self.stdout.write(f'\nProcessing Location: {location.customer.name} - {location.location_name}')

            company = self.get_company_for_entity(location.customer, location)
            if not company:
                self.stdout.write(self.style.WARNING(' Skipping: No company associated'))
                continue

            billing_start_date, billing_end_date = self.calculate_billing_period(
                location.start_date, billing_date, location.customer, location
            )
            if billing_start_date is None:
                self.stdout.write(self.style.WARNING(' No unbilled periods found - all caught up!'))
                continue

            monthly_periods = self.get_monthly_periods(billing_start_date, billing_end_date)
            self.stdout.write(self.style.SUCCESS(
                f' Found {len(monthly_periods)} monthly billing period(s): {billing_start_date} to {billing_end_date}'
            ))

            billing_records_data = []
            bills_created = 0
            bills_skipped = 0

            for period_start, period_end in monthly_periods:
                existing_bill = BillingRecord.objects.filter(
                    customer=location.customer,
                    customer_location=location,
                    billing_start_date=period_start,
                    billing_end_date=period_end
                ).first()
                if existing_bill:
                    self.stdout.write(self.style.WARNING(
                        f'   Bill already exists for period {period_start.strftime("%d-%m-%Y")} to '
                        f'{period_end.strftime("%d-%m-%Y")} - Bill ID: {existing_bill.id}'
                    ))
                    bills_skipped += 1
                    continue

                subscription_changes = self.get_subscription_changes_in_period(
                    location.customer, location, period_start, period_end
                )
                if subscription_changes:
                    self.stdout.write(self.style.WARNING(
                        f'   Found {len(subscription_changes)} subscription change(s) in this period'
                    ))

                sub_periods = self.split_period_by_changes(
                    period_start, period_end, subscription_changes, location.customer, location
                )

                total_base_amount = Decimal('0.00')
                for sp_start, sp_end, sp_plan, sp_amount in sub_periods:
                    period_amount = self.calculate_billing_amount_for_period(
                        sp_plan, sp_amount, sp_start, sp_end
                    )
                    total_base_amount += period_amount
                    days = (sp_end - sp_start).days + 1
                    plan_name = sp_plan.name if sp_plan else "None"
                    amount_used = sp_amount if sp_amount else (sp_plan.price if sp_plan else 0)
                    self.stdout.write(self.style.SUCCESS(
                        f'      {sp_start.strftime("%d-%m-%Y")} to {sp_end.strftime("%d-%m-%Y")} '
                        f'({days} days): {plan_name} @ Rs {amount_used}/month = Rs {period_amount:.2f}'
                    ))

                # ── FIX 4: GST based on company.gst_registered for locations too ──
                gst_details = self.get_gst_details(company, location.customer, location)
                amounts = self.calculate_gst(total_base_amount, gst_details)

                total_bill_amount = amounts['total_amount']
                customer = location.customer

                if hasattr(customer, 'advance_amount'):
                    advance_adjustment = self.adjust_advance_amount(customer, total_bill_amount)
                    paid_amount = advance_adjustment['paid_amount']
                    balance_amount = advance_adjustment['balance_amount']
                    discount_amount = advance_adjustment['advance_used']
                else:
                    paid_amount = Decimal('0.00')
                    balance_amount = total_bill_amount
                    discount_amount = Decimal('0.00')
                    advance_adjustment = {
                        'original_amount': total_bill_amount,
                        'advance_used': Decimal('0.00'),
                        'final_amount': total_bill_amount,
                        'remaining_advance': Decimal('0.00'),
                        'paid_amount': Decimal('0.00'),
                        'balance_amount': total_bill_amount,
                    }

                due_date = billing_date + timedelta(days=15)

                if not dry_run:
                    # ── FIX 1: paid=False always ─────────────────
                    billing_record = BillingRecord.objects.create(
                        customer=location.customer,
                        customer_location=location,
                        amount=total_bill_amount,
                        discount_amount=discount_amount,
                        gst_amount=amounts['total_gst'],
                        gst_type=gst_details['gst_type'],
                        paid_amount=paid_amount,
                        balance_amount=balance_amount,
                        billing_date=billing_date,
                        due_date=due_date,
                        billing_start_date=period_start,
                        billing_end_date=period_end,
                        paid=False,   # FIX 1
                    )

                    self.create_bill_items_for_billing_record(billing_record, sub_periods, gst_details)

                    # ── FIX 2: always Pending, no payment_date ───
                    status = 'Pending'
                    payment_mode = 'Advance Adjustment' if discount_amount > 0 else None
                    payment_date = None   # FIX 2

                    gst_note = (
                        f"GST Type: {gst_details['gst_type']}\n"
                        f"CGST (9%): {amounts['cgst']:.2f}\n"
                        f"SGST (9%): {amounts['sgst']:.2f}\n"
                        f"IGST (18%): {amounts['igst']:.2f}\n"
                        f"Total GST: {amounts['total_gst']:.2f}\n"
                        if gst_details.get('gst_applicable')
                        else "GST: Not Applicable (Company not GST registered)\n"
                    )

                    details_text = f"""=== BILL GENERATED ===

Customer: {location.customer.name}
Location: {location.location_name}
Company: {company.name}
Invoice Number: IN-{billing_record.id}

Billing Period: {period_start.strftime('%d-%m-%Y')} to {period_end.strftime('%d-%m-%Y')}
Billing Date: {billing_date.strftime('%d-%m-%Y')}
Due Date: {due_date.strftime('%d-%m-%Y')}

"""
                    if subscription_changes:
                        details_text += "Subscription Changes:\n"
                        for change in subscription_changes:
                            old_plan = change.old_subscription_plan.name if change.old_subscription_plan else "None"
                            new_plan = change.new_subscription_plan.name if change.new_subscription_plan else "None"
                            details_text += f"  {change.change_date}: {old_plan} to {new_plan}\n"
                        details_text += "\n"

                    details_text += f"""Financial Summary:
Base Amount: {amounts['base_amount']:.2f}
{gst_note}Total Amount: {total_bill_amount:.2f}
Advance Adjusted: {paid_amount:.2f}
Balance Amount: {balance_amount:.2f}
Status: {status}
"""

                    # ── FIX 3: is_approved=False ─────────────────
                    data_logs.objects.create(
                        user=None,
                        location=location,
                        customer=location.customer,
                        billing_record=billing_record,
                        payment_amount=paid_amount,
                        billing_period_start=period_start,
                        billing_period_end=period_end,
                        balance_amount=balance_amount,
                        status=status,
                        payment_mode=payment_mode,
                        payment_date=None,       # FIX 2
                        total_paid=paid_amount,
                        is_payment=True,
                        is_approved=False,       # FIX 3
                        action='Bill Generated',
                        details=details_text.strip()
                    )

                    amounts['subtotal'] = total_bill_amount
                    amounts['advance_used'] = discount_amount
                    amounts['total_amount'] = balance_amount
                    amounts['sub_periods'] = sub_periods

                    pdf_buffer = self.generate_invoice_pdf(
                        billing_record,
                        location.subscription_plan,
                        location.customer,
                        company,
                        gst_details,
                        amounts,
                        location=location,
                        advance_adjustment=advance_adjustment,
                        sub_periods=sub_periods
                    )

                    billing_records_data.append({
                        'billing_record': billing_record,
                        'pdf_buffer': pdf_buffer,
                        'amounts': amounts,
                        'period_start': period_start,
                        'period_end': period_end
                    })

                    bills_created += 1
                    self.stdout.write(self.style.SUCCESS(
                        f'   Bill #{billing_record.id} created - '
                        f'{period_start.strftime("%d-%m-%Y")} to {period_end.strftime("%d-%m-%Y")}, '
                        f'Total: Rs {total_bill_amount}, Advance: Rs {paid_amount}, Balance: Rs {balance_amount}'
                    ))
                else:
                    self.stdout.write(self.style.WARNING(
                        f'   [DRY RUN] Would generate bill - {period_start} to {period_end}, '
                        f'Total: Rs {amounts["total_amount"]}'
                    ))
                    bills_created += 1

            if bills_created > 0 or bills_skipped > 0:
                self.stdout.write(self.style.SUCCESS(
                    f' Summary: {bills_created} bill(s) created, {bills_skipped} skipped'
                ))

            if not dry_run and billing_records_data:
                email = location.location_email or location.customer.email
                self.send_consolidated_billing_email(
                    recipient_email=email,
                    recipient_name=location.customer.name,
                    billing_records_data=billing_records_data,
                    subscription_plan=location.subscription_plan,
                    entity_type='Customer Location',
                    entity=location.customer,
                    company=company,
                    gst_details=gst_details,
                    location=location
                )
                processed += 1
            elif bills_created > 0 and dry_run:
                processed += 1

        return processed

    # ─────────────────────────────────────────────────────────────
    # PDF GENERATION
    # ─────────────────────────────────────────────────────────────

    def safe_str(self, value):
        if not value:
            return ""
        for attr in ("name", "city_name", "state_name"):
            if hasattr(value, attr):
                return str(getattr(value, attr))
        return str(value)

    def generate_invoice_pdf(self, billing_record, subscription_plan, entity, company,
                              gst_details, amounts, location=None,
                              advance_adjustment=None, sub_periods=None):
        from reportlab.platypus import (
            SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image, KeepTogether
        )
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import inch
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_RIGHT, TA_LEFT
        from io import BytesIO
        import os

        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4,
                                rightMargin=30, leftMargin=30,
                                topMargin=30, bottomMargin=30)
        PAGE_W = A4[0] - doc.leftMargin - doc.rightMargin
        styles = getSampleStyleSheet()

        small_left = ParagraphStyle("small_left", parent=styles["Normal"],
                                    fontSize=9, leading=12, alignment=TA_LEFT)
        small_right = ParagraphStyle("small_right", parent=styles["Normal"],
                                     fontSize=9, leading=12, alignment=TA_RIGHT)
        desc_style = ParagraphStyle("desc", parent=styles["Normal"],
                                    fontSize=8, leading=10, alignment=TA_LEFT)

        elements = []

        # ── Header ───────────────────────────────────────────────
        logo = ""
        if getattr(company, "logo", None):
            try:
                logo_path = os.path.join(settings.MEDIA_ROOT, str(company.logo))
                if os.path.exists(logo_path):
                    logo = Image(logo_path, 1.2 * inch, 1.2 * inch)
            except Exception:
                pass

        # Show GSTIN only if GST registered
        gstin_line = (
            f"GSTIN: {self.safe_str(getattr(company, 'gst_number', ''))}"
            if gst_details.get('gst_applicable') else
            "GST: Not Registered"
        )

        # Invoice title — "TAX INVOICE" only if GST applicable, else "INVOICE"
        invoice_title = "TAX INVOICE" if gst_details.get('gst_applicable') else "INVOICE"

        company_name_block = Paragraph(
            f'<font size="16"><b>{company.name}</b></font><br/>'
            f'<font size="9">'
            f'{self.safe_str(getattr(company, "address", ""))}<br/>'
            f'Contact: {self.safe_str(getattr(company, "contact", ""))}<br/>'
            f'{gstin_line}'
            f'</font>',
            small_left
        )

        invoice_block = Paragraph(
            f'<b>{invoice_title}</b><br/>'
            f'<font size="9">Original for Recipient</font><br/><br/>'
            f'<b>IN-{billing_record.id}</b>',
            ParagraphStyle("hdr", fontSize=14, alignment=TA_RIGHT, fontName="Helvetica-Bold")
        )

        header = Table(
            [[logo, company_name_block, invoice_block]],
            colWidths=[1.5 * inch, PAGE_W * 0.45, PAGE_W * 0.30]
        )
        header.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(header)
        elements.append(Spacer(1, 10))

        # ── Amount Due Banner ─────────────────────────────────────
        final_amount = amounts.get('total_amount', amounts.get('subtotal', Decimal('0.00')))
        if isinstance(final_amount, str):
            final_amount = Decimal(final_amount)

        amount_due = Table(
            [[
                Paragraph("<b>Amount Due</b>", small_left),
                Paragraph(
                    f"<b>Rs {final_amount:,.2f}</b>",
                    ParagraphStyle("amt", fontSize=14, alignment=TA_RIGHT,
                                   textColor=colors.white, fontName="Helvetica-Bold")
                )
            ]],
            colWidths=[PAGE_W * 0.55, PAGE_W * 0.45]
        )
        amount_due.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#2f5f7a")),
            ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("RIGHTPADDING", (0, 0), (-1, -1), 10),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(amount_due)
        elements.append(Spacer(1, 12))

        # ── Company + Dates ───────────────────────────────────────
        company_block = Paragraph(
            f'<b>{company.name}</b><br/>'
            f'{getattr(company, "address", "")}<br/>'
            f'{gstin_line}',
            small_left
        )
        date_block = Paragraph(
            f'Issue Date: {billing_record.billing_date.strftime("%d-%m-%Y")}<br/>'
            f'Due Date: {billing_record.due_date.strftime("%d-%m-%Y")}',
            small_right
        )
        company_info = Table([[company_block, date_block]],
                              colWidths=[PAGE_W * 0.62, PAGE_W * 0.38])
        company_info.setStyle(TableStyle([
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
        ]))
        elements.append(company_info)
        elements.append(Spacer(1, 10))

        # ── Client Details ────────────────────────────────────────
        entity_obj = billing_record.customer
        client_name_block = Paragraph(
            f'<b>Client Details</b><br/>'
            f'<b>{self.safe_str(entity_obj.name)}</b><br/>'
            f'Email: {self.safe_str(getattr(entity_obj, "email", ""))}<br/>',
            small_left
        )

        if location:
            address = location.area or location.address
            city, state, pincode = location.city, location.state, location.pincode
        else:
            address = entity_obj.address
            city, state, pincode = entity_obj.city, entity_obj.state, entity_obj.pincode

        billing_address_block = Paragraph(
            f'<b>Billing Address</b><br/>'
            f'{self.safe_str(address)}<br/>'
            f'{self.safe_str(city)}, {self.safe_str(state)}<br/>'
            f'{self.safe_str(pincode)}',
            small_right
        )

        client_billing_row = Table(
            [[client_name_block, billing_address_block]],
            colWidths=[PAGE_W * 0.5, PAGE_W * 0.5]
        )
        client_billing_row.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("ALIGN", (1, 0), (1, 0), "RIGHT"),
        ]))
        elements.append(client_billing_row)
        elements.append(Spacer(1, 12))

        # ── Billing Table ─────────────────────────────────────────
        # FIX: GST columns only if GST applicable
        gst_applicable = gst_details.get('gst_applicable', False)

        if gst_applicable:
            if gst_details["is_same_state"]:
                headers = ["S.No", "Item Description", "Price", "Taxable", "CGST @ 9%", "SGST @ 9%", "Amount"]
                col_ratios = (0.07, 0.30, 0.12, 0.12, 0.12, 0.12, 0.13)
            else:
                headers = ["S.No", "Item Description", "Price", "Taxable", "IGST @ 18%", "Amount"]
                col_ratios = (0.07, 0.33, 0.12, 0.13, 0.15, 0.20)
        else:
            # No GST — simplified table
            headers = ["S.No", "Item Description", "Price", "Amount"]
            col_ratios = (0.07, 0.50, 0.20, 0.23)

        table_rows = [headers]

        if sub_periods and len(sub_periods) > 1:
            for idx, (sp_start, sp_end, sp_plan, sp_amount) in enumerate(sub_periods, 1):
                if not sp_plan:
                    continue
                period_text = f"{sp_start.strftime('%d-%m-%Y')} to {sp_end.strftime('%d-%m-%Y')}"
                days = (sp_end - sp_start).days + 1
                base_amt = self.calculate_billing_amount_for_period(sp_plan, sp_amount, sp_start, sp_end)
                amount_text = f"Custom: Rs {sp_amount}/month" if sp_amount else f"Rs {sp_plan.price}/month"
                desc_html = (
                    f"{sp_plan.name}<br/>"
                    f"<font size='7'>Period: {period_text} ({days} days)<br/>{amount_text}</font>"
                )
                if gst_applicable:
                    if gst_details["is_same_state"]:
                        row = [str(idx), Paragraph(desc_html, desc_style),
                               f"{base_amt:,.2f}", f"{base_amt:,.2f}", "-", "-", f"{base_amt:,.2f}"]
                    else:
                        row = [str(idx), Paragraph(desc_html, desc_style),
                               f"{base_amt:,.2f}", f"{base_amt:,.2f}", "-", f"{base_amt:,.2f}"]
                else:
                    row = [str(idx), Paragraph(desc_html, desc_style),
                           f"{base_amt:,.2f}", f"{base_amt:,.2f}"]
                table_rows.append(row)
        else:
            period_text = (
                f"{billing_record.billing_start_date.strftime('%d-%m-%Y')} to "
                f"{billing_record.billing_end_date.strftime('%d-%m-%Y')}"
            )
            base_amt = amounts['base_amount']
            if isinstance(base_amt, str):
                base_amt = Decimal(base_amt)

            desc_html = f"{subscription_plan.name}<br/><font size='7'>Period: {period_text}</font>"
            if gst_applicable:
                if gst_details["is_same_state"]:
                    row = ["1", Paragraph(desc_html, desc_style),
                           f"{base_amt:,.2f}", f"{base_amt:,.2f}", "-", "-", f"{base_amt:,.2f}"]
                else:
                    row = ["1", Paragraph(desc_html, desc_style),
                           f"{base_amt:,.2f}", f"{base_amt:,.2f}", "-", f"{base_amt:,.2f}"]
            else:
                row = ["1", Paragraph(desc_html, desc_style),
                       f"{base_amt:,.2f}", f"{base_amt:,.2f}"]
            table_rows.append(row)

        items_table = Table(
            table_rows,
            colWidths=[PAGE_W * x for x in col_ratios],
            repeatRows=1
        )
        items_table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), 0.7, colors.grey),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2f5f7a")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]))
        elements.append(items_table)
        elements.append(Spacer(1, 8))

        # ── GST Summary (only if GST applicable) ─────────────────
        subtotal_before_gst = amounts['base_amount']
        if isinstance(subtotal_before_gst, str):
            subtotal_before_gst = Decimal(subtotal_before_gst)

        subtotal_with_gst = amounts.get('subtotal', amounts['total_amount'])
        if isinstance(subtotal_with_gst, str):
            subtotal_with_gst = Decimal(subtotal_with_gst)

        num_cols = len(headers)
        blank_cols = [""] * (num_cols - 2)

        gst_summary_data = [
            blank_cols + ["Subtotal (Before Tax):", f"Rs {subtotal_before_gst:,.2f}"],
        ]

        if gst_applicable:
            if gst_details["is_same_state"]:
                cgst_val = amounts['cgst'] if isinstance(amounts['cgst'], Decimal) else Decimal(amounts['cgst'])
                sgst_val = amounts['sgst'] if isinstance(amounts['sgst'], Decimal) else Decimal(amounts['sgst'])
                gst_summary_data.append(blank_cols + ["CGST @ 9%:", f"Rs {cgst_val:,.2f}"])
                gst_summary_data.append(blank_cols + ["SGST @ 9%:", f"Rs {sgst_val:,.2f}"])
            else:
                igst_val = amounts['igst'] if isinstance(amounts['igst'], Decimal) else Decimal(amounts['igst'])
                gst_summary_data.append(blank_cols + ["IGST @ 18%:", f"Rs {igst_val:,.2f}"])
            gst_summary_data.append(blank_cols + ["Total (With Tax):", f"Rs {subtotal_with_gst:,.2f}"])
        else:
            gst_summary_data.append(blank_cols + ["GST:", "Not Applicable"])
            gst_summary_data.append(blank_cols + ["Total:", f"Rs {subtotal_with_gst:,.2f}"])

        gst_summary_table = Table(
            gst_summary_data,
            colWidths=[PAGE_W * x for x in col_ratios]
        )
        gst_summary_table.setStyle(TableStyle([
            ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
            ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("LINEABOVE", (-2, -1), (-1, -1), 1.5, colors.HexColor("#2f5f7a")),
        ]))
        elements.append(gst_summary_table)
        elements.append(Spacer(1, 8))

        # ── Advance Adjustment ────────────────────────────────────
        if advance_adjustment and Decimal(str(advance_adjustment.get('advance_used', 0))) > 0:
            adv_used = amounts.get('advance_used', Decimal('0.00'))
            if isinstance(adv_used, str):
                adv_used = Decimal(adv_used)

            advance_table_data = [
                blank_cols + ["Advance Adjusted:", f"- Rs {adv_used:,.2f}"],
                blank_cols + ["Balance Due:", f"Rs {final_amount:,.2f}"],
            ]
            advance_table = Table(
                advance_table_data,
                colWidths=[PAGE_W * x for x in col_ratios]
            )
            advance_table.setStyle(TableStyle([
                ("ALIGN", (-2, 0), (-1, -1), "RIGHT"),
                ("FONTNAME", (-2, -1), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LINEABOVE", (-2, -1), (-1, -1), 1.5, colors.HexColor("#2f5f7a")),
                ("TEXTCOLOR", (-2, 0), (-1, 0), colors.green),
            ]))
            elements.append(advance_table)
            elements.append(Spacer(1, 12))

        # ── Bank Info ─────────────────────────────────────────────
        bank_name = getattr(company, 'bank_name', '') or 'Not Provided'
        account_number = getattr(company, 'account_number', '') or 'Not Provided'
        ifsc_code = getattr(company, 'ifsc_code', '') or 'Not Provided'
        branch_name = getattr(company, 'branch_name', '')

        bank_info = (
            f"<b>Account Holder:</b> {company.name}<br/>"
            f"<b>Bank:</b> {bank_name}<br/>"
        )
        if branch_name:
            bank_info += f"<b>Branch:</b> {branch_name}<br/>"
        bank_info += (
            f"<b>A/C:</b> {account_number}<br/>"
            f"<b>IFSC:</b> {ifsc_code}"
        )

        bank_block = Paragraph(bank_info, small_left)
        amount_words = Paragraph(
            f"<b>Amount in Words</b><br/>{self.number_to_words(final_amount)}",
            small_left
        )
        elements.append(Table(
            [[bank_block, amount_words]],
            colWidths=[PAGE_W * 0.55, PAGE_W * 0.45]
        ))
        elements.append(Spacer(1, 10))

        # ── QR Code + Payment Terms ───────────────────────────────
        qr_img = ""
        if getattr(company, 'qr_code', None):
            try:
                qr_path = os.path.join(settings.MEDIA_ROOT, str(company.qr_code))
                if os.path.exists(qr_path):
                    qr_img = Image(qr_path, 1.6 * inch, 1.6 * inch)
            except Exception:
                pass

        payment_terms = Paragraph(
            "<b>Payment Terms</b><br/>"
            "Payment due within 15 days<br/>"
            "Late payment charges applicable<br/>"
            "Mention Invoice Number during payment",
            ParagraphStyle("payment_right", parent=small_left, alignment=TA_RIGHT)
        )

        if qr_img:
            elements.append(KeepTogether([
                Table([[qr_img, payment_terms]], colWidths=[PAGE_W * 0.35, PAGE_W * 0.65])
            ]))
        else:
            elements.append(payment_terms)

        elements.append(Spacer(1, 16))
        elements.append(Paragraph(
            f"<b>For {company.name}</b><br/><br/>Authorized Signatory",
            ParagraphStyle("sign", alignment=TA_RIGHT, fontSize=10)
        ))

        doc.build(elements)
        buffer.seek(0)
        return buffer

    # ─────────────────────────────────────────────────────────────
    # NUMBER TO WORDS
    # ─────────────────────────────────────────────────────────────

    def number_to_words(self, number):
        if isinstance(number, str):
            number = Decimal(number)

        ones  = ['', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight', 'Nine']
        tens  = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
        teens = ['Ten', 'Eleven', 'Twelve', 'Thirteen', 'Fourteen', 'Fifteen',
                 'Sixteen', 'Seventeen', 'Eighteen', 'Nineteen']

        def below_hundred(n):
            if n < 10:   return ones[n]
            if n < 20:   return teens[n - 10]
            return tens[n // 10] + (' ' + ones[n % 10] if n % 10 else '')

        def below_thousand(n):
            if n < 100: return below_hundred(n)
            return ones[n // 100] + ' Hundred' + (' ' + below_hundred(n % 100) if n % 100 else '')

        if number == 0:
            return 'Zero Only'

        integer_part = int(number)
        decimal_part = int(round((number - integer_part) * 100))
        result = []

        for divisor, label in [(10000000, 'Crore'), (100000, 'Lakh'), (1000, 'Thousand')]:
            if integer_part >= divisor:
                result.append(below_thousand(integer_part // divisor) + f' {label}')
                integer_part %= divisor

        if integer_part > 0:
            result.append(below_thousand(integer_part))

        words = ' '.join(result)
        if decimal_part > 0:
            words += f' and {below_hundred(decimal_part)} Paise'
        return words + ' Only'

    # ─────────────────────────────────────────────────────────────
    # EMAIL
    # ─────────────────────────────────────────────────────────────

    def send_consolidated_billing_email(self, recipient_email, recipient_name,
                                        billing_records_data, subscription_plan,
                                        entity_type, entity, company, gst_details,
                                        location=None, contact_person=None):
        total_amount_all_bills = sum(
            Decimal(str(d['amounts']['total_amount'])) for d in billing_records_data
        )
        subject = (
            f'Tax Invoices ({len(billing_records_data)} Bills) - {subscription_plan.name} Plan'
            if len(billing_records_data) > 1
            else f'Tax Invoice - {subscription_plan.name} Plan'
        )

        html_content = self.get_consolidated_email_html(
            recipient_name=contact_person or recipient_name,
            entity_type=entity_type,
            entity=entity,
            company=company,
            subscription_plan=subscription_plan,
            billing_records_data=billing_records_data,
            total_amount_all_bills=total_amount_all_bills,
            gst_details=gst_details,
            location=location
        )

        try:
            email_msg = EmailMultiAlternatives(
                subject=subject,
                body=strip_tags(html_content),
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[recipient_email]
            )
            email_msg.attach_alternative(html_content, "text/html")

            for data in billing_records_data:
                br = data['billing_record']
                month_year = data['period_start'].strftime('%b_%Y')
                email_msg.attach(
                    f"Invoice_IN-{br.id}_{month_year}.pdf",
                    data['pdf_buffer'].getvalue(),
                    'application/pdf'
                )

            email_msg.send()
            self.stdout.write(self.style.SUCCESS(
                f'  Consolidated email with {len(billing_records_data)} PDF(s) sent to {recipient_email}'
            ))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'  Failed to send email: {str(e)}'))

    def get_consolidated_email_html(self, recipient_name, entity_type, entity, company,
                                    subscription_plan, billing_records_data,
                                    total_amount_all_bills, gst_details, location=None):
        location_info = f" - {location.location_name}" if location else ""
        entity_name = recipient_name + location_info

        gst_applicable = gst_details.get('gst_applicable', False)
        gst_type_info = (
            ("Same State - CGST (9%) + SGST (9%)" if gst_details['is_same_state']
             else "Interstate - IGST (18%)")
            if gst_applicable
            else "Not Applicable (Company not GST registered)"
        )

        invoice_rows = ""
        for data in billing_records_data:
            br = data['billing_record']
            amounts = data['amounts']
            period_text = (
                f"{data['period_start'].strftime('%d-%m-%Y')} to "
                f"{data['period_end'].strftime('%d-%m-%Y')}"
            )
            base_amt  = Decimal(str(amounts['base_amount']))
            gst_amt   = Decimal(str(amounts['total_gst']))
            total_amt = Decimal(str(amounts['total_amount']))
            sub_periods = amounts.get('sub_periods', [])
            change_indicator = " Change" if sub_periods and len(sub_periods) > 1 else ""

            gst_cell = f"Rs {gst_amt:,.2f}" if gst_applicable else "N/A"

            invoice_rows += f"""
            <tr style="border-bottom:1px solid #e9ecef;">
                <td style="padding:12px 8px;">IN-{br.id}{change_indicator}</td>
                <td style="padding:12px 8px;">{period_text}</td>
                <td style="padding:12px 8px;">Rs {base_amt:,.2f}</td>
                <td style="padding:12px 8px;">{gst_cell}</td>
                <td style="padding:12px 8px;font-weight:bold;">Rs {total_amt:,.2f}</td>
            </tr>"""

        html = f"""<!DOCTYPE html>
<html>
<head><meta charset="UTF-8">
<style>
body{{font-family:Arial,sans-serif;line-height:1.6;color:#333;max-width:650px;margin:0 auto;padding:20px;}}
.header{{background-color:#3d6a8e;color:white;padding:25px;text-align:center;border-radius:5px 5px 0 0;}}
.content{{background-color:#f8f9fa;padding:30px;border:1px solid #dee2e6;}}
.invoice-summary{{background-color:white;padding:20px;border-radius:5px;margin:20px 0;}}
.invoice-table{{width:100%;border-collapse:collapse;margin:15px 0;}}
.invoice-table th{{background-color:#3d6a8e;color:white;padding:12px 8px;text-align:left;font-weight:600;font-size:13px;}}
.invoice-table td{{padding:12px 8px;font-size:14px;}}
.total-amount{{font-size:26px;font-weight:bold;color:#3d6a8e;text-align:center;padding:25px;
  background:linear-gradient(135deg,#e7f1ff 0%,#d0e7ff 100%);border-radius:8px;margin:25px 0;border:2px solid #3d6a8e;}}
.attachment-note{{background-color:#fff3cd;border-left:4px solid #ffc107;padding:15px;margin:20px 0;border-radius:4px;}}
.attachment-list{{background-color:#f8f9fa;padding:15px;border-radius:4px;margin:15px 0;}}
.attachment-list ul{{margin:10px 0;padding-left:20px;}}
.attachment-list li{{padding:5px 0;}}
.info-box{{background-color:#e7f3ff;border-left:4px solid #0d6efd;padding:15px;margin:20px 0;border-radius:4px;}}
.footer{{text-align:center;color:#6c757d;font-size:12px;margin-top:30px;padding-top:20px;border-top:1px solid #dee2e6;}}
.detail-row{{display:flex;justify-content:space-between;padding:8px 0;border-bottom:1px solid #e9ecef;}}
.detail-label{{font-weight:bold;color:#6c757d;}}
</style>
</head>
<body>
<div class="header">
  <h1>{company.name}</h1>
  <p style="font-size:16px;margin:5px 0;">Invoice{'s' if len(billing_records_data)>1 else ''} Notification</p>
  <p style="font-size:14px;margin:5px 0;opacity:0.9;">{len(billing_records_data)} Invoice{'s' if len(billing_records_data)>1 else ''} Generated</p>
</div>
<div class="content">
  <p style="font-size:16px;"><strong>Dear {recipient_name},</strong></p>
  <p>{'Multiple invoices have' if len(billing_records_data)>1 else 'A new invoice has'} been generated for your subscription with {company.name}.</p>
  <div class="invoice-summary">
    <div class="detail-row"><span class="detail-label">{entity_type}:</span><span>{entity_name}</span></div>
    <div class="detail-row"><span class="detail-label">Subscription Plan:</span><span>{subscription_plan.name}</span></div>
    <div class="detail-row"><span class="detail-label">Number of Invoices:</span><span>{len(billing_records_data)}</span></div>
    <div class="detail-row"><span class="detail-label">GST:</span><span>{gst_type_info}</span></div>
  </div>
  <h3 style="color:#3d6a8e;margin-top:25px;">Invoice Details</h3>
  <p style="font-size:12px;color:#666;margin:5px 0;">Change = Invoice contains subscription plan changes</p>
  <table class="invoice-table">
    <thead>
      <tr>
        <th>Invoice #</th><th>Billing Period</th><th>Base Amount</th>
        <th>GST</th><th>Amount Due</th>
      </tr>
    </thead>
    <tbody>{invoice_rows}</tbody>
  </table>
  <div class="total-amount">Total Amount Due: Rs {total_amount_all_bills:,.2f}</div>
  <div class="attachment-note">
    <strong>{len(billing_records_data)} PDF Invoice{'s' if len(billing_records_data)>1 else ''} Attached</strong>
  </div>
  <div class="attachment-list">
    <strong>Attached Documents:</strong><ul>"""

        latest_due_date = max(d['billing_record'].due_date for d in billing_records_data)

        for data in billing_records_data:
            br = data['billing_record']
            total_amt = Decimal(str(data['amounts']['total_amount']))
            sub_periods = data['amounts'].get('sub_periods', [])
            change_note = " - Contains subscription changes" if sub_periods and len(sub_periods) > 1 else ""
            html += (
                f"<li>Invoice IN-{br.id} - "
                f"{data['period_start'].strftime('%d-%m-%Y')} to "
                f"{data['period_end'].strftime('%d-%m-%Y')} "
                f"(Rs {total_amt:,.2f}){change_note}</li>"
            )

        invoice_ids = ', '.join(f'IN-{d["billing_record"].id}' for d in billing_records_data)

        html += f"""    </ul>
  </div>
  <div class="info-box">
    <p style="margin:0;"><strong>Important Information:</strong></p>
    <ul style="margin:10px 0;padding-left:20px;">
      <li>All invoices are due by <strong>{latest_due_date.strftime('%d-%m-%Y')}</strong></li>
      <li>Please include the respective invoice number when making payments</li>
      <li>Scan the QR code in each PDF for quick payment</li>
    </ul>
  </div>
  <p><strong>Payment Instructions:</strong></p>
  <ul style="line-height:1.8;">
    <li>Total payment due: <strong>Rs {total_amount_all_bills:,.2f}</strong></li>
    <li>Payment deadline: <strong>{latest_due_date.strftime('%d-%m-%Y')}</strong></li>
    <li>When paying, mention invoice numbers: {invoice_ids}</li>
    <li>For queries, contact us at {company.email} or {company.contact}</li>
  </ul>
  <p style="margin-top:25px;">Thank you for your continued business!</p>
  <p>Best regards,<br><strong>{company.name} Team</strong></p>
</div>
<div class="footer">
  <p>This is an automated message. Please do not reply to this email.</p>
  <p>{company.name} | {company.contact} | {company.email}</p>
  <p>Copyright {datetime.now().year} {company.name}. All rights reserved.</p>
</div>
</body>
</html>"""
        return html