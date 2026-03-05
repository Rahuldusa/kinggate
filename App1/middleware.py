# class CompanyFilterMiddleware:
#     """
#     Middleware to attach filter parameters to every request.
#     Ensures company IDs are always integers.
#     """
#     def __init__(self, get_response):
#         self.get_response = get_response

#     def __call__(self, request):
#         # Get GST type from session
#         request.gst_type = request.session.get('gst_type', '')
        
#         # Get selected companies and ensure they're integers
#         selected_companies = request.session.get('selected_companies', [])
        
#         if selected_companies:
#             company_ids = []
#             for c in selected_companies:
#                 try:
#                     # Convert to int if it's a string
#                     company_id = int(c) if isinstance(c, str) else c
#                     company_ids.append(company_id)
#                 except (ValueError, TypeError) as e:
#                     print(f"Warning: Could not convert '{c}' to int: {e}")
#             request.selected_companies = company_ids
#         else:
#             request.selected_companies = []
        
#         # Debug logging (skip static files)
#         if not request.path.startswith('/static/'):
#             print(f"→ {request.path}")
#             print(f"  GST: '{request.gst_type}' | Companies: {request.selected_companies}")
        
#         response = self.get_response(request)
#         return response


class CompanyFilterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ✅ Fixed: use the same keys as the helper functions
        request.gst_type = request.session.get('selected_gst_type', 'gst')

        selected_companies = request.session.get('selected_company_ids', [])
        if selected_companies:
            company_ids = []
            for c in selected_companies:
                try:
                    company_ids.append(int(c))
                except (ValueError, TypeError) as e:
                    print(f"Warning: Could not convert '{c}' to int: {e}")
            request.selected_companies = company_ids
        else:
            request.selected_companies = []

        if not request.path.startswith('/static/'):
            print(f"→ {request.path}")
            print(f"  GST: '{request.gst_type}' | Companies: {request.selected_companies}")

        response = self.get_response(request)
        return response