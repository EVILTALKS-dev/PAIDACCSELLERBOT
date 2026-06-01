import qrcode
import io
import random
from config import UPI_ID, UPI_NAME


def make_upi_qr(amount: float, order_ref: str):
    """
    Generate UPI QR with a small unique paise (1-9 paise only)
    so admin can identify payment without confusing the user.
    Returns (image_bytes, exact_amount)
    """
    # Only 1-9 paise extra — barely noticeable
    paise = random.randint(1, 9)
    exact = round(float(amount) + paise / 100, 2)

    upi_string = (
        f"upi://pay?"
        f"pa={UPI_ID}&"
        f"pn={UPI_NAME.replace(' ', '%20')}&"
        f"am={exact:.2f}&"
        f"cu=INR&"
        f"tn=Ref{order_ref}"
    )

    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=4,
    )
    qr.add_data(upi_string)
    qr.make(fit=True)

    img = qr.make_image(fill_color="#111111", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return buf.read(), exact
