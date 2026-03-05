from django.db.models import Q
from .models import Company

def get_filtered_companies(request):
    """
    Get companies filtered by GST type and selected company IDs.
    
    Logic:
    - If GST type is selected but no companies: show all companies of that GST type
    - If companies are selected: show only those companies (with GST filter if applicable)
    - If nothing selected: show all companies
    """
    gst_type = getattr(request, 'gst_type', '')
    selected_companies = getattr(request, 'selected_companies', [])
    
    print(f"\n{'='*60}")
    print(f"get_filtered_companies()")
    print(f"GST Type: '{gst_type}'")
    print(f"Selected Companies: {selected_companies}")
    
    # Start with all companies
    companies_query = Company.objects.all()
    print(f"Total companies in DB: {companies_query.count()}")
    
    # Apply filters based on what's selected
    if selected_companies:
        # Companies are specifically selected - filter to those IDs
        companies_query = companies_query.filter(id__in=selected_companies)
        print(f"After company ID filter: {companies_query.count()}")
        
        # Also apply GST filter if specified
        if gst_type == 'gst':
            companies_query = companies_query.filter(gst_registered=True)
            print(f"After GST=True filter: {companies_query.count()}")
        elif gst_type == 'non-gst':
            companies_query = companies_query.filter(gst_registered=False)
            print(f"After GST=False filter: {companies_query.count()}")
    
    elif gst_type:
        # Only GST type is selected - show ALL companies of that type
        if gst_type == 'gst':
            companies_query = companies_query.filter(gst_registered=True)
            print(f"Showing all GST companies: {companies_query.count()}")
        elif gst_type == 'non-gst':
            companies_query = companies_query.filter(gst_registered=False)
            print(f"Showing all Non-GST companies: {companies_query.count()}")
    
    else:
        # Nothing selected - show all companies
        print(f"No filters applied - showing all companies: {companies_query.count()}")
    
    # Show sample results
    for comp in companies_query.values('id', 'name', 'gst_registered')[:5]:
        print(f"  - ID:{comp['id']} {comp['name']} (GST:{comp['gst_registered']})")
    
    if companies_query.count() > 5:
        print(f"  ... and {companies_query.count() - 5} more")
    
    print(f"{'='*60}\n")
    
    return companies_query


def get_company_filter_context(request):
    """
    Return context data for templates to show current filter state.
    """
    return {
        'selected_gst_type': getattr(request, 'gst_type', ''),
        'selected_company_ids': getattr(request, 'selected_companies', []),
    }