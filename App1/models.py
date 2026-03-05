from django.db import models
from django.contrib.auth.hashers import make_password



class Roles(models.Model):
    role_name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True, null=True)
    
    def _str_(self):
        return self.role_name
class RolePermissions(models.Model):  

    role = models.ForeignKey(Roles, on_delete=models.CASCADE, related_name='permissions')

    dashboard_v = models.BooleanField(default=False)

    customer_management_v = models.BooleanField(default=False)
    customer_management_a = models.BooleanField(default=False)
    customer_management_e = models.BooleanField(default=False)
    customer_management_d = models.BooleanField(default=False)

    company_master_v = models.BooleanField(default=False)
    company_master_a = models.BooleanField(default=False)
    company_master_e = models.BooleanField(default=False)
    company_master_d = models.BooleanField(default=False)

    subscription_master_v = models.BooleanField(default=False)
    subscription_master_a = models.BooleanField(default=False)
    subscription_master_e = models.BooleanField(default=False)
    subscription_master_d = models.BooleanField(default=False)

    billing_invoices_v = models.BooleanField(default=False)
    billing_invoices_a = models.BooleanField(default=False)
    billing_invoices_e = models.BooleanField(default=False)
    billing_invoices_d = models.BooleanField(default=False)

    roles_v = models.BooleanField(default=False)
    roles_a = models.BooleanField(default=False)
    roles_e = models.BooleanField(default=False)
    roles_d = models.BooleanField(default=False)

    users_v = models.BooleanField(default=False)
    users_a = models.BooleanField(default=False)
    users_e = models.BooleanField(default=False)
    users_d = models.BooleanField(default=False)

    # Manual Receipts — View + Add only
    manual_receipts_v = models.BooleanField(default=False)
    manual_receipts_a = models.BooleanField(default=False)  # NEW

    # Payment Approval — all 4
    payment_approval_v = models.BooleanField(default=False)
    payment_approval_a = models.BooleanField(default=False)  # NEW
    payment_approval_e = models.BooleanField(default=False)
    payment_approval_d = models.BooleanField(default=False)  # NEW

    reports_v = models.BooleanField(default=False)

    data_logs_v = models.BooleanField(default=False)
    user_logs_v = models.BooleanField(default=False)

    settings_v = models.BooleanField(default=False)

    def __str__(self):
        return f"Permissions for {self.role.role_name}"


class Custom_User(models.Model):
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(unique=True)
    role = models.ForeignKey(Roles, on_delete=models.SET_NULL, null=True, blank=True)
    password = models.CharField(max_length=240)
    name = models.CharField(max_length=200, blank=True)
    phone_number = models.CharField(max_length=20, blank=True)


    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith('pbkdf2_'):
            self.password = make_password(self.password)

        super().save(*args, **kwargs)


    def __str__(self):
        return self.username


class SubscriptionPlan(models.Model):
    

    name = models.CharField(max_length=50, null=False, blank=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(Custom_User, on_delete=models.SET_NULL, null=True, blank=True, related_name='created_subscription_plans')
    updated_by = models.ForeignKey(Custom_User, on_delete=models.SET_NULL, null=True, blank=True, related_name='updated_subscription_plans')
    price = models.DecimalField(max_digits=10, decimal_places=2)
    def __str__(self):
        return self.name



class State(models.Model):
    name = models.CharField(max_length=100, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'State'
        verbose_name_plural = 'States'
    
    def __str__(self):
        return self.name
    


class City(models.Model):
    name = models.CharField(max_length=100)
    state = models.ForeignKey(State, on_delete=models.CASCADE, related_name='cities')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'City'
        verbose_name_plural = 'Cities'
        unique_together = ['name', 'state'] 
    
    def __str__(self):
        return f"{self.name}, {self.state.name}"
    


class Area(models.Model):
    name = models.CharField(max_length=100)
    city = models.ForeignKey(City, on_delete=models.CASCADE, related_name='areas')
    pincode = models.CharField(max_length=10, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = 'Area'
        verbose_name_plural = 'Areas'
        unique_together = ['name', 'city']  
    
    def __str__(self):
        return f"{self.name}, {self.city.name}"


    



class Company(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    contact = models.CharField(max_length=20)
    email = models.EmailField()
    gst_registered = models.BooleanField(default=False)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    qr_code=models.ImageField( blank=True, null=True)
    bank_name=models.CharField(max_length=200, blank=True, null=True)
    account_number=models.CharField(max_length=50, blank=True, null=True)
    ifsc_code=models.CharField(max_length=20, blank=True, null=True)
    branch_name=models.CharField(max_length=200, blank=True, null=True)
    Contact_person=models.CharField(max_length=200, blank=True, null=True)
    contact_person_email=models.EmailField(blank=True, null=True)
    contact_person_phone=models.CharField(max_length=20, blank=True, null=True)
    contact_2=models.CharField(max_length=20, blank=True, null=True)
    start_date=models.DateField(blank=True, null=True)
    status=models.CharField(max_length=50, blank=True, null=True)
    logo= models.ImageField( blank=True, null=True)
    location_link=models.CharField(max_length=500, blank=True, null=True)
    processing_fee=models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    def __str__(self):
        return self.name
    



    
    @property
    def full_address(self):
        """Returns the full address of the billing location"""
        location = self.customer_location or self.company_location
        if location:
            parts = [
                location.address,
                location.area,
                str(location.city) if location.city else None,
                str(location.state) if location.state else None,
                location.pincode
            ]
            return ", ".join(filter(None, parts))
        return "No Address"

class SubscriptionChange(models.Model):
    """Track subscription plan changes for customers and locations"""
    customer = models.ForeignKey('Customer', on_delete=models.CASCADE, related_name='subscription_changes')
    customer_location = models.ForeignKey('CustomerLocation', on_delete=models.CASCADE, null=True, blank=True, related_name='subscription_changes')
    
    # Old subscription details
    old_subscription_plan = models.ForeignKey('SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='old_changes')
    old_custom_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # New subscription details
    new_subscription_plan = models.ForeignKey('SubscriptionPlan', on_delete=models.SET_NULL, null=True, blank=True, related_name='new_changes')
    new_custom_amount = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    # Change metadata
    change_date = models.DateField()
    change_reason = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey('Custom_User', on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-change_date']
        verbose_name = 'Subscription Change'
        verbose_name_plural = 'Subscription Changes'
    
    def __str__(self):
        entity = f"{self.customer.name}"
        if self.customer_location:
            entity += f" - {self.customer_location.location_name}"
        old_plan = self.old_subscription_plan.name if self.old_subscription_plan else "None"
        new_plan = self.new_subscription_plan.name if self.new_subscription_plan else "None"
        return f"{entity}: {old_plan} → {new_plan} on {self.change_date}"
    
    def get_old_amount(self):
        """Get the old subscription amount"""
        if self.old_custom_amount:
            return self.old_custom_amount
        elif self.old_subscription_plan:
            return self.old_subscription_plan.price
        return Decimal('0.00')
    
    def get_new_amount(self):
        """Get the new subscription amount"""
        if self.new_custom_amount:
            return self.new_custom_amount
        elif self.new_subscription_plan:
            return self.new_subscription_plan.price
        return Decimal('0.00')

class Customer(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    email = models.EmailField()
    gst_registered = models.BooleanField(default=False)
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    location_link = models.CharField(max_length=500, blank=True, null=True)
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, blank=True, null=True)
    start_date = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=50, blank=True, null=True)
    subscription_plan = models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    outstanding_amount = models.DecimalField(
    max_digits=10, decimal_places=2, default=0.00, null=True, blank=True
)
    # New field for custom subscription amount
    custom_subscription_amount = models.DecimalField(
        max_digits=10, 
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Custom amount that overrides the default subscription plan price"
    )
    previous_subscription_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='previous_customers'
    )
    upgrade_date = models.DateField(blank=True, null=True)
    
    remarks = models.TextField(blank=True, null=True)
    advance_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    def __str__(self):
        return self.name
    
    def get_subscription_amount(self):
        """Get the subscription amount - custom if set, otherwise plan default"""
        if self.custom_subscription_amount:
            return self.custom_subscription_amount
        elif self.subscription_plan:
            return self.subscription_plan.price
        return 0
    def save(self, *args, **kwargs):
        """Track subscription changes when plan or custom amount changes"""
        is_new = self.pk is None
        
        if not is_new:
            # Get the old instance from database
            try:
                old_instance = Customer.objects.get(pk=self.pk)
                
                # Check if subscription plan or custom amount changed
                plan_changed = old_instance.subscription_plan != self.subscription_plan
                amount_changed = old_instance.custom_subscription_amount != self.custom_subscription_amount
                
                if plan_changed or amount_changed:
                    # Create subscription change record
                    SubscriptionChange.objects.create(
                        customer=self,
                        old_subscription_plan=old_instance.subscription_plan,
                        old_custom_amount=old_instance.custom_subscription_amount,
                        new_subscription_plan=self.subscription_plan,
                        new_custom_amount=self.custom_subscription_amount,
                        change_date=date.today(),
                        change_reason="Subscription plan or amount updated"
                    )
            except Customer.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)
    

class CustomerContact(models.Model):
    customer = models.ForeignKey(Customer, related_name="contacts", on_delete=models.CASCADE)
    phone_number = models.CharField(max_length=20)

    def __str__(self):
        return f"{self.customer.name} - {self.phone_number}"

    

class CustomerLocation(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='locations')
    
    location_link=models.CharField(max_length=500, blank=True, null=True)
    location_name = models.CharField(max_length=200, help_text="e.g., Head Office, Branch 1, Warehouse")
    address = models.TextField()
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    gst_registered = models.BooleanField(
        default=False,
        help_text="Whether this location is GST registered"
    )
    gst_number = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="GST registration number (required if gst_registered is True)"
    )
    subscription_plan=models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    location_contact = models.CharField(max_length=20, blank=True, null=True)
    location_email = models.EmailField(blank=True, null=True)
    start_date=models.DateField(blank=True, null=True)
    remarks=models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    custom_subscription_amount = models.DecimalField(
        max_digits=10,
        decimal_places=2, 
        blank=True, 
        null=True,
        help_text="Custom amount that overrides the default subscription plan price"
    )
    outstanding_amount = models.DecimalField(
        max_digits=10,  
        decimal_places=2, 
        default=0
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location_name']
        verbose_name = 'Customer Location'
        verbose_name_plural = 'Customer Locations'
    
    def __str__(self):
        return f"{self.customer.name} - {self.location_name}"
    def save(self, *args, **kwargs):
        is_new = self.pk is None
        
        if not is_new:
            # Get the old instance from database
            try:
                old_instance = CustomerLocation.objects.get(pk=self.pk)
                
                # Check if subscription plan or custom amount changed
                plan_changed = old_instance.subscription_plan != self.subscription_plan
                amount_changed = old_instance.custom_subscription_amount != self.custom_subscription_amount
                
                if plan_changed or amount_changed:
                    # Create subscription change record
                    SubscriptionChange.objects.create(
                        customer=self.customer,
                        customer_location=self,
                        old_subscription_plan=old_instance.subscription_plan,
                        old_custom_amount=old_instance.custom_subscription_amount,
                        new_subscription_plan=self.subscription_plan,
                        new_custom_amount=self.custom_subscription_amount,
                        change_date=date.today(),
                        change_reason="Subscription plan or amount updated"
                    )
            except CustomerLocation.DoesNotExist:
                pass
        
        super().save(*args, **kwargs)



class CompanyLocation(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name='locations')
    location_link=models.CharField(max_length=500, blank=True, null=True)
   
    location_name = models.CharField(max_length=200, help_text="e.g., Head Office, Branch 1, Factory")
    address = models.TextField()
    area = models.ForeignKey(Area, on_delete=models.SET_NULL, null=True, blank=True)
    city = models.ForeignKey(City, on_delete=models.SET_NULL, null=True, blank=True)
    state = models.ForeignKey(State, on_delete=models.SET_NULL, null=True, blank=True)
    pincode = models.CharField(max_length=10, blank=True, null=True)
    
    subscription_plan=models.ForeignKey(SubscriptionPlan, on_delete=models.SET_NULL, null=True, blank=True)
    start_date=models.DateField(blank=True, null=True)
    location_contact = models.CharField(max_length=20, blank=True, null=True)
    location_email = models.EmailField(blank=True, null=True)
    location_contact_person = models.CharField(max_length=200, blank=True, null=True)
    
    processing_fee=models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['location_name']
        verbose_name = 'Company Location'
        verbose_name_plural = 'Company Locations'
    
    def __str__(self):
        return f"{self.company.name} - {self.location_name}"
    
from datetime import date
from django.db import models
from datetime import date
from decimal import Decimal


from django.db import models
from datetime import date
from decimal import Decimal

class BillingRecord(models.Model):
    PAYMENT_MODES = [
        ('cash', 'Cash'),
        ('upi', 'UPI'),
        ('card', 'Card'),
        ('netbanking', 'Net Banking'),
        ('cheque', 'Cheque'),
        
    ]
    
    GST_TYPES = [
        ('INTRA-STATE', 'Intra-State (CGST + SGST)'),
        ('INTER-STATE', 'Inter-State (IGST)'),
        ('NONE', 'No GST'),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_records')
    customer_location = models.ForeignKey(CustomerLocation, on_delete=models.SET_NULL, null=True, blank=True, related_name='billing_records')
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # New GST fields
    gst_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    gst_type = models.CharField(max_length=20, choices=GST_TYPES, default='NONE')
    
    billing_date = models.DateField(default=date.today)
    due_date = models.DateField()
    
    billing_start_date = models.DateField(null=True, blank=True)
    billing_end_date = models.DateField(null=True, blank=True)
    paid = models.BooleanField(default=False)
    payment_date = models.DateField(null=True, blank=True)
    payment_mode = models.CharField(max_length=100, choices=PAYMENT_MODES, null=True, blank=True)
    transaction_id = models.CharField(max_length=200, blank=True, null=True)
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    invoice_number = models.CharField(max_length=100, blank=True, null=True, unique=True)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-billing_date']
        verbose_name = 'Billing Record'
        verbose_name_plural = 'Billing Records'

    def __str__(self):
        client_name = self.client_name
        location_name = self.location_name
        
        if location_name != "No Location":
            return f"Billing: {client_name} - {location_name} on {self.billing_date}"
        return f"Billing: {client_name} on {self.billing_date}"
    
    @staticmethod
    def generate_invoice_number():
        """Generate invoice number in format INV-YYYY-XXX"""
        current_year = date.today().year
        
        # Get the last invoice for the current year
        last_invoice = BillingRecord.objects.filter(
            invoice_number__startswith=f'INV-{current_year}-'
        ).order_by('-invoice_number').first()
        
        if last_invoice and last_invoice.invoice_number:
            # Extract the sequence number from the last invoice
            try:
                last_sequence = int(last_invoice.invoice_number.split('-')[-1])
                new_sequence = last_sequence + 1
            except (ValueError, IndexError):
                new_sequence = 1
        else:
            # First invoice of the year
            new_sequence = 1
        
        # Format: INV-YYYY-XXX (with leading zeros)
        return f'INV-{current_year}-{new_sequence:03d}'
    
    def save(self, *args, **kwargs):
        """Override save to auto-generate invoice number if not present"""
        if not self.invoice_number:
            self.invoice_number = self.generate_invoice_number()
        
        super().save(*args, **kwargs)
    
    @property
    def client_name(self):
        """Returns the name of the customer"""
        if self.customer:
            return self.customer.name
        return "Unknown"
    
    @property
    def location_name(self):
        """Returns the location name if available"""
        if self.customer_location:
            return self.customer_location.location_name
        return "No Location"
    
    @property
    def full_address(self):
        """Returns the full address of the billing location or customer"""
        location = self.customer_location
        
        if location:
            parts = [
                location.address,
                str(location.area) if location.area else None,
                str(location.city) if location.city else None,
                str(location.state) if location.state else None,
                location.pincode
            ]
            return ", ".join(filter(None, parts))
        
        # Fallback to customer address
        if self.customer:
            parts = [
                self.customer.address,
                str(self.customer.area) if hasattr(self.customer, 'area') and self.customer.area else None,
                str(self.customer.city) if hasattr(self.customer, 'city') and self.customer.city else None,
                str(self.customer.state) if hasattr(self.customer, 'state') and self.customer.state else None,
                self.customer.pincode if hasattr(self.customer, 'pincode') else None
            ]
            return ", ".join(filter(None, parts))
        
        return "No Address"
    
    @property
    def billing_entity(self):
        """Returns the entity being billed"""
        if self.customer_location:
            return {
                'type': 'customer_location',
                'name': f"{self.customer.name} - {self.customer_location.location_name}",
                'entity': self.customer_location
            }
        elif self.customer:
            return {
                'type': 'customer',
                'name': self.customer.name,
                'entity': self.customer
            }
        return None
    
    def calculate_totals(self):
        """Calculate and update the total amount from bill items"""
        items = self.bill_items.all()
        subtotal = sum(item.total_price for item in items)
        
        # Use stored GST amount instead of calculating from items
        # Formula: Total = Subtotal + GST - Discount
        self.amount = subtotal + self.gst_amount - self.discount_amount
        self.save(update_fields=['amount'])
    
    @property
    def subtotal(self):
        """Calculate subtotal from all items (without tax)"""
        return sum(item.total_price for item in self.bill_items.all())
    
    @property
    def total_tax(self):
        """Returns the stored GST amount"""
        return self.gst_amount
    
    @property
    def cgst_amount(self):
        """Calculate CGST amount (only for INTRA-STATE)"""
        if self.gst_type == 'INTRA-STATE':
            return self.gst_amount / 2
        return Decimal('0.00')
    
    @property
    def sgst_amount(self):
        """Calculate SGST amount (only for INTRA-STATE)"""
        if self.gst_type == 'INTRA-STATE':
            return self.gst_amount / 2
        return Decimal('0.00')
    
    @property
    def igst_amount(self):
        """Calculate IGST amount (only for INTER-STATE)"""
        if self.gst_type == 'INTER-STATE':
            return self.gst_amount
        return Decimal('0.00')


class BillItem(models.Model):
    billing_record = models.ForeignKey(BillingRecord, on_delete=models.CASCADE, related_name='bill_items')
    
    # Item Details
    item_name = models.CharField(max_length=200)
    description = models.TextField(blank=True, null=True)
    
    # Quantity and Pricing
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    
    # Tax
    tax_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    # Calculated fields
    total_price = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    tax_amount = models.DecimalField(max_digits=10, decimal_places=2, editable=False)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['id']
        verbose_name = 'Bill Item'
        verbose_name_plural = 'Bill Items'
    
    def __str__(self):
        return f"{self.item_name} - {self.quantity} x {self.unit_price}"
    
    def save(self, *args, **kwargs):
        from decimal import Decimal
        
        # Convert all values to Decimal to ensure proper calculation
        quantity = Decimal(str(self.quantity))
        unit_price = Decimal(str(self.unit_price))
        tax_percentage = Decimal(str(self.tax_percentage))
        
        # Calculate total price (quantity * unit_price)
        self.total_price = (quantity * unit_price).quantize(Decimal('0.01'))
        
        # Calculate tax amount: (total_price * tax_percentage) / 100
        self.tax_amount = (self.total_price * tax_percentage / Decimal('100')).quantize(Decimal('0.01'))
        
        super().save(*args, **kwargs)
        
        # Update billing record totals
        if self.billing_record:
            self.billing_record.calculate_totals()

class customer_cameras(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    seriak_number = models.CharField(max_length=200)
    customer_location = models.ForeignKey(CustomerLocation, on_delete=models.SET_NULL, null=True, blank=True)


class Organization(models.Model):
    name = models.CharField(max_length=200)
    address = models.TextField()
    contact = models.CharField(max_length=20)
    email = models.EmailField()
    gst_number = models.CharField(max_length=20, blank=True, null=True)
    logo= models.ImageField( blank=True, null=True)
    cin_number=models.CharField(max_length=20, blank=True, null=True)
    State=models.CharField(max_length=100, blank=True, null=True)

    def __str__(self):
        return self.name
    
# Updated data_logs model - Replace your existing data_logs model with this

class data_logs(models.Model):
    user = models.ForeignKey(Custom_User, on_delete=models.SET_NULL, null=True, blank=True)
    action = models.CharField(max_length=200, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True)
    location = models.ForeignKey(CustomerLocation, on_delete=models.SET_NULL, null=True, blank=True)
    billing_record = models.ForeignKey(BillingRecord, on_delete=models.SET_NULL, null=True, blank=True)
    payment_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    billing_period_start = models.DateField(blank=True, null=True)
    billing_period_end = models.DateField(blank=True, null=True)
    status = models.CharField(max_length=100, blank=True, null=True)
    payment_mode = models.CharField(max_length=100, blank=True, null=True)
    payment_date = models.DateField(blank=True, null=True)
    total_paid = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    balance_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    discount_given = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    receipt_number = models.CharField(max_length=100, blank=True, null=True)
    is_upgrade = models.BooleanField(default=False)
    old_subscription_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='old_plan_logs'
    )
    new_subscription_plan = models.ForeignKey(
        SubscriptionPlan, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='new_plan_logs'
    )
    upgrade_amount = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    
    # Payment approval fields
    is_payment = models.BooleanField(default=False)
    is_approved = models.BooleanField(default=False)
    transaction_id = models.CharField(max_length=200, blank=True, null=True)
    payment_notes = models.TextField(blank=True, null=True)
    
    # Approval tracking
    submitted_by = models.ForeignKey(
        Custom_User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='submitted_payment_logs'
    )
    approved_by = models.ForeignKey(
        Custom_User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='approved_payment_logs'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        if self.customer:
            return f"{self.action} - {self.customer.name} - {self.timestamp}"
        return f"{self.action} - {self.timestamp}"


  
class user_logs(models.Model):
    user = models.CharField(max_length=200, null=True, blank=True)
    action = models.CharField(max_length=200, null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        if self.user:
            return f"{self.action} - {self.user} - {self.timestamp}"
        return f"{self.action} - {self.timestamp}"