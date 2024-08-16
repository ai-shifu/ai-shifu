from .models import Contact
import uuid
from flask import Flask
from ...dao import db


def add_contact(app: Flask, user_id: str, name: str, mobile: str, email: str,  telephone: str = '', position: str = '', company: str = ''):
    with app.app_context():
        current_contact = Contact.query.filter_by(
            user_id=user_id, name=name).first()
        if current_contact:
            if email and email != "":
                current_contact.email = email
            if telephone and telephone != "":
                current_contact.telephone = telephone
            if mobile and mobile != "":
                current_contact.mobile = mobile
            if position and position != "":
                current_contact.position = position
            if company and company != "":
                current_contact.company = company
            db.session.commit()
            return current_contact

        contact_id = str(uuid.uuid4())
        new_contact = Contact(
            user_id=user_id,
            contact_id=contact_id,
            name=name,
            email=email,
            telephone=telephone,
            mobile=mobile,
            position=position,
            company=company
        )
        db.session.add(new_contact)
        db.session.commit()
        return new_contact


class ContactInfo:
    def __init__(self, contact_id, name, email, telephone, mobile, position, company):
        self.contact_id = contact_id
        self.name = name
        self.email = email
        self.telephone = telephone
        self.mobile = mobile
        self.position = position
        self.company = company

    def __json__(self):
        return {
            'contact_id': self.contact_id,
            'name': self.name,
            'email': self.email,
            'telephone': self.telephone,
            'mobile': self.mobile,
            'position': self.position,
            'company': self.company
        }

    def __str__(self) -> str:
        pass

    def __html__(self):
        return self.__json__()


def get_contact(app: Flask, user_id: str, name: str):
    with app.app_context():
        contact = Contact.query.filter_by(user_id=user_id, name=name).first()
        if contact:
            return ContactInfo(
                contact_id=contact.contact_id,
                name=contact.name,
                email=contact.email,
                telephone=contact.telephone,
                mobile=contact.mobile,
                position=contact.position,
                company=contact.company
            )
        else:
            return None


def get_all_contacts(app: Flask, user_id: str, name: str, mobile: str, email: str):
    with app.app_context():
        contacts = Contact.query.filter_by(user_id=user_id).filter(
            Contact.name.like('%'+name+'%'),
            Contact.mobile.like('%'+mobile+'%'),
            Contact.email.like('%'+email+'%')).all()
        return [ContactInfo(
            contact_id=contact.contact_id,
            name=contact.name,
            email=contact.email,
            telephone=contact.telephone,
            mobile=contact.mobile,
            position=contact.position,
            company=contact.company
        ) for contact in contacts]


def update_contact(app: Flask, contact_id: str, name: str, mobile: str, email: str):
    print(contact_id)
    with app.app_context():
        contact = db.session.query(Contact).filter_by(
            contact_id=contact_id).first()
        if contact:
            contact.name = name
            contact.mobile = mobile
            contact.email = email
            db.session.commit()


def delete_contact(app: Flask, contact_ids: str):
    contact_ids_array = contact_ids.split(',')
    with app.app_context():
        for contact_id in contact_ids_array:
            contact = db.session.query(Contact).filter_by(
                contact_id=contact_id).first()
            if contact:
                db.session.delete(contact)
        db.session.commit()
