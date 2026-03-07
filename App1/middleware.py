
import logging

logger = logging.getLogger(__name__)

class CompanyFilterMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        request.gst_type = request.session.get('selected_gst_type', 'gst')

        selected_companies = request.session.get('selected_company_ids', [])

        if selected_companies:
            company_ids = []
            for c in selected_companies:
                try:
                    company_ids.append(int(c))
                except (ValueError, TypeError) as e:
                    logger.warning(f"Could not convert '{c}' to int: {e}")

            request.selected_companies = company_ids
        else:
            request.selected_companies = []

        if not request.path.startswith('/static/'):
            logger.info(f"Path: {request.path}")
            logger.info(f"GST: {request.gst_type} | Companies: {request.selected_companies}")

        response = self.get_response(request)
        return response