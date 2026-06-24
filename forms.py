# forms.py — declarative FlaskForm classes. the input-validation layer that sits
# between the browser and the routes. each class declares its fields + rules once;
# the routes just ask "is this valid?" instead of hand-parsing request.form.

from flask_wtf import FlaskForm                    # base class — every form inherits this (like db.Model for tables)
from flask_wtf.file import FileField, FileAllowed  # file-aware field + the validator that replaces allowed_file()
from wtforms import (
    StringField, PasswordField, TextAreaField,
    SelectField, HiddenField, SubmitField,
)
from wtforms.validators import DataRequired, Length, Optional, ValidationError


def strip_whitespace(value):                       # mirrors the .strip() you did by hand in every route
    return value.strip() if isinstance(value, str) else value


class LoginForm(FlaskForm):                         # only checks fields are PRESENT — credential check stays on the route
    username = StringField("Username", validators=[DataRequired()], filters=[strip_whitespace])
    password = PasswordField("Password", validators=[DataRequired()])   # no strip — spaces may be intentional
    submit = SubmitField("Log in")


class RegistrationForm(FlaskForm):
    username = StringField(
        "Username",
        validators=[DataRequired(), Length(min=3, max=80)],   # max=80 matches the db.String(80) column. min=3 is a NEW rule
        filters=[strip_whitespace],
    )
    password = PasswordField("Password", validators=[DataRequired(), Length(min=6)])  # min=6 is a NEW rule
    submit = SubmitField("Register")

    def validate_username(self, field):            # WTForms auto-calls validate_<fieldname> during validation
        from app import User, db                   # DEFERRED import → dodges the circular import (models live in app.py)
        existing = db.session.scalar(
            db.select(User).where(User.username == field.data)
        )
        if existing:
            raise ValidationError("That username is already taken.")


class ReportForm(FlaskForm):
    hazard_type = SelectField(
        "Hazard type",
        choices=[                                  # this list IS the allow-list now — junk values rejected automatically
            ("", "-- Select Option --"),           # placeholder: valid choice but empty → DataRequired catches it
            ("pothole", "Pothole"),
            ("streetlight", "Broken streetlight"),
            ("garbage", "Garbage"),
            ("flooding", "Flooding"),
        ],
        validators=[DataRequired()],
    )
    location = StringField(
        "Location",
        validators=[DataRequired(), Length(max=255)],   # max=255 matches the db.String(255) column
        filters=[strip_whitespace],
    )
    description = TextAreaField("Description", validators=[Optional()], filters=[strip_whitespace])  # optional free text
    photo = FileField(
        "Photo (optional)",
        validators=[FileAllowed(["jpg", "jpeg", "png", "gif"], "Photo must be a JPG, PNG, or GIF.")],
    )
    latitude = HiddenField()                       # JS writes here. renders id="latitude" → getElementById still works
    longitude = HiddenField()                      # no validators: optional + JS-controlled. route still float()-checks
    submit = SubmitField("Submit report")