import factory
from factory import Faker

from src.models.delivery_log import DeliveryLog, DeliveryStatus
from src.models.notification import Notification, Priority, Status
from src.models.user import User
from src.models.user_channel import ChannelType, UserChannel


# ModelFactory — базовый класс factory_boy для SQLAlchemy моделей.
# Каждый атрибут класса описывает как генерировать значение поля.
class UserFactory(factory.Factory):
    # указываем какую модель создаёт эта фабрика
    class Meta:
        model = User

    # Faker генерирует реалистичные случайные данные
    username = Faker("user_name")  # "john_doe_42"
    email = Faker("email")  # "john@example.com"
    password_hash = "test-password-hash"
    telegram_id = Faker("random_int", min=100000000, max=999999999)
    phone = Faker("phone_number")  # "+7 (999) 123-45-67"
    is_active = True


class UserChannelFactory(factory.Factory):
    class Meta:
        model = UserChannel

    # LazyAttribute — значение вычисляется на основе других полей объекта
    # здесь user_id берётся из связанного UserFactory
    user_id = factory.LazyAttribute(lambda o: o.user.id)
    channel = ChannelType.EMAIL
    is_enabled = True


class NotificationFactory(factory.Factory):
    class Meta:
        model = Notification

    user_id = factory.LazyAttribute(lambda o: o.user.id)
    # Sequence гарантирует уникальность — каждый вызов даёт новый ключ
    # "idempotency-key-0", "idempotency-key-1", "idempotency-key-2"...
    idempotency_key = factory.Sequence(lambda n: f"idempotency-key-{n}")
    title = Faker("sentence", nb_words=4)  # "Your order has been placed"
    body = Faker("paragraph")  # несколько предложений
    priority = Priority.NORMAL
    status = Status.PENDING


class DeliveryLogFactory(factory.Factory):
    class Meta:
        model = DeliveryLog

    notification_id = factory.LazyAttribute(lambda o: o.notification.id)
    channel = ChannelType.EMAIL
    status = DeliveryStatus.PENDING
    attempts = 0
    last_error = None
    sent_at = None
