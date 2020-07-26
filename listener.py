import os
import json
import sentry_sdk
from woocommerce import API
import klaviyo
from dotenv import load_dotenv
from flask import Flask, request, Response
from sentry_sdk.integrations.flask import FlaskIntegration


load_dotenv()

sentry_sdk.init(
    dsn=os.getenv('SENTRY_DSN'),
    integrations=[FlaskIntegration()]
)

WCAPI = API(
    url=os.getenv('WC_URL'),
    consumer_key=os.getenv('WC_K'),
    consumer_secret=os.getenv('WC_S'),
    version="wc/v3"
)

APP = Flask(__name__)

CLIENT = klaviyo.Klaviyo(public_token=os.getenv(
    'KLAVIYO_PUBLIC_TOKEN'), private_token=os.getenv('KLAVIYO_PRIVATE_TOKEN'))

IP_LISTS = json.loads(os.environ['ALLOWED_IP_ADDRESSES'])


def lookup(json_object, search_term):
    return [obj['value'] for obj in json_object if obj['key'] == search_term]


@APP.route('/order/<action>', methods=['POST'])
def push_data(action):
    access_ip = request.access_route[0]
    data = request.json
    if action == 'orderCreated':
        event = 'New Woocommerce Order'

        for counter, item in enumerate(data['line_items']):
            if item['sku'] == 'retroconsole-en':
                design = lookup(item['meta_data'], 'Design').lower()
                image_url = f'{os.getenv("CLOUDFRONT_URL")}/cp/en/{design}.jpg'
            else:
                req = WCAPI.get(f'products/{item["id"]}').json()
                image_url = req['images'][0]['src']

            data['line_items'][counter].update({'product_img_url': image_url})

    elif action == 'orderUpdated' and data['status'] == 'completed':
        event = "Fulfilled Woocommerce Order"
    elif action == 'orderUpdated' and data['status'] == 'refunded':
        event = "Refunded Woocpmmerce Order"
    elif action == 'orderUpdated' and data['status'] == 'cancelled':
        event = "Cancelled Woocommerce Order"
    elif action == 'orderUpdated' and data['status'] == 'processing':
        return Response(status=202)

    try:
        if access_ip in IP_LISTS:
            customer = data['billing']
            print(access_ip)
            print(IP_LISTS)
            CLIENT.Public.track(event,
                                email=customer['email'],
                                properties=data,
                                customer_properties={
                                    '$email': customer['email'],
                                    '$first_name': customer['first_name'],
                                    '$last_name': customer['last_name'],
                                    '$phone_number': customer['phone'],
                                    '$address1': customer['address_1'],
                                    '$address2': customer['address_2'],
                                    '$city': customer['city'],
                                    '$zip': customer['postcode'],
                                    '$region': customer['state'],
                                    '$country': customer['country']
                                })

            return Response(status=200)
        else:
            response = APP.response_class(
                response=json.dumps(
                    f' (your ip ({access_ip}) is not allowed to make calls.'),
                status=403,
                mimetype='application/json'
            )
            return response
    except TypeError:
        return Response(status=404)
