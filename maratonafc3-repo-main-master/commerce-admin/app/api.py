from datetime import datetime, timedelta
import requests
import logging
from rest_framework import viewsets, mixins, exceptions, status
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from app.models import Customer, PaymentGateway, Checkout, PagarmeGateway
from app.serializers import CustomerSerializer, PaymentGatewaySerializer, CheckoutSerializer
from commerce_admin import settings
from tenant.utils import get_tenant

logger = logging.getLogger(__name__)

class TenantViewSet(viewsets.GenericViewSet):
    def check_permissions(self, request):
        tenant = get_tenant()
        if not tenant:
            raise exceptions.PermissionDenied(detail='Tenant not defined')
        super().check_permissions(request)


class CustomerViewSet(TenantViewSet, mixins.CreateModelMixin):
    queryset = Customer.objects.all()
    serializer_class = CustomerSerializer


class PaymentGatewayViewSet(TenantViewSet, mixins.ListModelMixin):
    queryset = PaymentGateway.objects.all()
    serializer_class = PaymentGatewaySerializer

    def list(self, request, *args, **kwargs):
        instance = self.get_queryset().filter(default=True).first()
        if not instance:
            raise NotFound(detail="Payment gateway not found", code=404)
        serializer = self.get_serializer(instance)
        return Response(serializer.data)


class CheckoutViewSet(TenantViewSet, mixins.CreateModelMixin):
    queryset = Checkout.objects.all()
    serializer_class = CheckoutSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        payment_method = serializer.instance.payment_method
        customer_address = serializer.instance.customer_address

        try:
            r = requests.post(
                settings.MICRO_SERVICE_PAYMENT_URL,
                json={
                    "secret_key": settings.MICRO_SERVICE_PAYMENT_API_KEY,
                    "gateway": {
                        "name": "pagar.me",
                        'key': PagarmeGateway.objects.get(default=True).api_key,
                    },
                    "transaction_client_id": "123",
                    "payment_method": payment_method.name,
                    "amount": serializer.instance.total * 100,
                    "card_hash": request.data["card_hash"],
                    #"postback_url": ""
                    "installments": request.data["installments"],
                    "boleto_expiration_date": (datetime.now()+timedelta(days=2)).strftime('%Y-%m-%d'),
                    "soft_descriptor": get_tenant().company,
                    "capture": "true",
                    "boleto_instructions": "Não aceitar depois do vencimento",
                    "customer": {
                        "external_id": customer_address.id,
                        "name": customer_address.customer.name,
                        "email": customer_address.customer.email,
                        "country": "br",
                        "type": "individual",
                        "documents": {
                            "type": "cpf",
                            "number": customer_address.customer.personal_document
                        },
                        "phone_numbers": [
                            "%s %s" % (customer_address.ddd1, customer_address.phone1)
                        ]
                    },
                }
            )
            # if r.status_code == 200 or r.status_code == 201:
            #     serializer.instance.status = 2
            #     data = r.json()
            #     serializer.instance.bank_slip_url = data['boleto_url']
            #     # pegar a url do boleto
            #     serializer.instance.save()
            #else:
            # return Response(
            #     {
            #         'message': 'Pedido foi registrado, mas o pagamento não foi concluído. Entre em contato com a central de atendimento '
            #     },
            #     status=207
            # )
        except Exception as e:
            logger.exception(e)
            return Response(
                {
                    'message': 'Pedido foi registrado, mas o pagamento não foi concluído. Entre em contato com a central de atendimento '
                },
                status=207
            )
        headers = self.get_success_headers(serializer.data)
        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)
