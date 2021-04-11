from datetime import datetime, timedelta
from hashlib import md5
import json
import os
from time import time
from flask import current_app, url_for
from flask_login import UserMixin, current_user
from werkzeug.security import generate_password_hash, check_password_hash
import jwt
from app import db, login
from app.search import add_to_index, remove_from_index, query_index
from sqlalchemy import or_, and_, desc


class SearchableMixin(object):


    @classmethod
    def search(cls, expression, page, per_page):
        ids, total = query_index(cls.__tablename__, expression, page, per_page)
        if total == 0:
            return cls.query.filter_by(id=0), 0
        when = []
        for i in range(len(ids)):
            when.append((ids[i], i))
        return cls.query.filter(cls.id.in_(ids)).order_by(
            db.case(when, value=cls.id)), total


    @classmethod
    def before_commit(cls, session):
        session._changes = {
            'add': list(session.new),
            'update': list(session.dirty),
            'delete': list(session.deleted)
        }


    @classmethod
    def after_commit(cls, session):
        for obj in session._changes['add']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['update']:
            if isinstance(obj, SearchableMixin):
                add_to_index(obj.__tablename__, obj)
        for obj in session._changes['delete']:
            if isinstance(obj, SearchableMixin):
                remove_from_index(obj.__tablename__, obj)
        session._changes = None


    @classmethod
    def reindex(cls):
        for obj in cls.query:
            add_to_index(cls.__tablename__, obj)


db.event.listen(db.session, 'before_commit', SearchableMixin.before_commit)
db.event.listen(db.session, 'after_commit', SearchableMixin.after_commit)


class PaginatedAPIMixin(object):
    @staticmethod

    def to_collection_dict(query, page, per_page, endpoint, **kwargs):
        resources = query.paginate(page, per_page, False)
        data = {
                'items': [item.to_dict() for item in resources.items],
                '_meta':{
                         'page': page,
                         'per_page': per_page,
                         'total_pages': resources.pages,
                         'total_items': resources.total
                        },
                '_links':{
                          'self': url_for(endpoint, page=page, per_page=per_page, **kwargs),
                          'next': url_for(endpoint, page=page + 1, per_page=per_page, **kwargs) if resources.has_next else None,
                          'prev': url_for(endpoint, page=page - 1, per_page=per_page, **kwargs) if resources.has_prev else None
                         }
                }
        return data


likes_table_posts = db.Table('likes_table_posts', db.Model.metadata,
                        db.Column('id_user', db.Integer, db.ForeignKey('user.id')),
                        db.Column('id_post', db.Integer, db.ForeignKey('post.id'))
                        )


dislikes_table_posts = db.Table('dislikes_table_posts',  
                        db.Column('id_user', db.Integer, db.ForeignKey('user.id')),
                        db.Column('id_post', db.Integer, db.ForeignKey('post.id'))
                        )


likes_table_comments = db.Table('likes_table_comments', 
                        db.Column('id_user', db.Integer, db.ForeignKey('user.id')),
                        db.Column('id_comments', db.Integer, db.ForeignKey('comments.id'))
                        )


dislikes_table_comments = db.Table('dislikes_table_comments', 
                        db.Column('id_user', db.Integer, db.ForeignKey('user.id')),
                        db.Column('id_comments', db.Integer, db.ForeignKey('comments.id'))
                        )


read_later_table_posts = db.Table('read_later_table_posts', 
                        db.Column('id_user', db.Integer, db.ForeignKey('user.id')),
                        db.Column('id_post', db.Integer, db.ForeignKey('post.id'))
                        )


class User(UserMixin, PaginatedAPIMixin, db.Model):

    id = db.Column(db.Integer, primary_key=True) 
    username = db.Column(db.String(64), index=True)
    email = db.Column(db.String(120), index=True)
    password_hash = db.Column(db.String(128))
    status = db.Column(db.String(140))
    role = db.Column(db.Boolean, default=True)#if role==1 this user is administrator elif role==0 user is blocked
    liked_post = db.relationship('Post', secondary=likes_table_posts, 
                primaryjoin=(likes_table_posts.c.id_user==id), 
                backref=db.backref('liker', lazy='dynamic'),lazy='dynamic')
    disliked_post = db.relationship('Post', secondary=dislikes_table_posts, 
                    primaryjoin=(dislikes_table_posts.c.id_user==id),
                    backref=db.backref('disliker', lazy='dynamic'), lazy = 'dynamic')
    liked_comments = db.relationship('Comments', secondary=likes_table_comments,
                     primaryjoin=(likes_table_comments.c.id_user==id),
                     backref=db.backref('liker', lazy='dynamic'), lazy='dynamic')
    disliked_comments = db.relationship('Comments', secondary=dislikes_table_comments,
                        primaryjoin=(dislikes_table_comments.c.id_user==id), 
                        backref=db.backref('disliker', lazy='dynamic'), lazy='dynamic')
    read_later = db.relationship('Post', secondary=read_later_table_posts,
                 primaryjoin=(read_later_table_posts.c.id_user==id),
                 backref=db.backref('read_later', lazy='dynamic'), lazy='dynamic')
    last_seen = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    message_sent = db.relationship('PrivateMessages', foreign_keys='PrivateMessages.sender_id', backref='sender', lazy='dynamic')
    message_received = db.relationship('PrivateMessages', foreign_keys='PrivateMessages.recipient_id', backref='recipient', lazy='dynamic')
    registration_time = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    last_message_red_time = db.Column(db.DateTime)



    def set_password(self, password):
        self.password_hash = generate_password_hash(password)


    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


    def avatar(self, size):
        digest = md5(self.email.lower().encode('utf-8')).hexdigest()
        return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)


    def to_read_later(self):

        '''This method returns a list of posts postponed to later sorted by time.'''

        return self.read_later.filter(read_later_table_posts.c.id_user == self.id).order_by(Post.timestamp.desc())


    def liked_posts(self):

        """This method returns all liked posts, ordered by time."""

        return self.liked_post.filter(likes_table_posts.c.id_user == self.id).order_by(Post.timestamp.desc())
      
    
    def reputation(self):

        """This method returns the user's reputation, which 
        is equal to the difference between likes and dislikes"""

        return self.liked_comments.count()-self.disliked_comments.count()


    def like_this_comments(self, comment):
        if comment not in self.tlked_comments:
            if comment in self.disliked_comments(comment):
                self.disliked_comments.remove(comment)
            else: 
                self.liked_comments.append(comment)



    def dislike_this_comments(self, comment):
        if not self.this_comments_disliked(comment):
            if self.this_comments_liked(comment):
                self.liked_comments.remove(comment)
            else:
                self.disliked_comments.append(comment)

    

    def new_messages(self):
        last_read_time = self.last_message_red_time or datetime(1900, 1, 1)


    def get_reset_password_token(self, expires_in=600):
        return jwt.encode(
            {'reset_password': self.id, 'exp': time() + expires_in},
            current_app.config['SECRET_KEY'],
            algorithm='HS256').decode('utf-8')


    @staticmethod
    def verify_reset_password_token(token):
        try:
            id = jwt.decode(token, current_app.config['SECRET_KEY'],
                            algorithms=['HS256'])['reset_password']
        except:
            return
        return User.query.get(id)

 

class Post(SearchableMixin, db.Model):

    __searchable__ = ['body','title', 'description', 'section']
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), index=True)
    body = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    section = db.Column(db.String(120), index=True)
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)
    vievs = db.Column(db.Integer, default=0)
    number_of_coments = db.Column(db.Integer, default=0)#
    version = db.Column(db.Integer, default=0)#Sestem posts version control
    language = db.Column(db.String(10), index=True)
    title_image = db.Column(db.String(140))
    description = db.Column(db.String(160))#description post
    selected_posts = db.Column(db.Boolean, default=False)
    hidden_post = db.Column(db.Boolean, default=True)#If hidden_post is set to True, this post is not displayed to users


    def coin_likes(self):
        return db.session.query(likes_table_posts).filter(likes_table_posts.c.id_post == self.id).count() 


    def coin_dislikes(self):
        return db.session.query(dislikes_table_posts).filter(dislikes_table_posts.c.id_post == self.id).count() 


    def coin_read_later(self):
        return db.session.query(read_later_table_posts).filter(read_later_table_posts.c.id_post == self.id).count()


    def commented(self):
        return Comments.query.filter_by(post_id=self.id).count()


    def all_sections():
        return Post.query.with_entities(Post.section).distinct()
 

    def vievs_upper(self):
        self.vievs +=  1
        db.session.commit()
            

class Comments(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    body = db.Column(db.String(180))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    post_id = db.Column(db.Integer, db.ForeignKey('post.id'))
    likes = db.Column(db.Integer, default=0)
    dislikes = db.Column(db.Integer, default=0)


    def coin_likes(self,):
        return db.session.query(likes_table_comments).filter(likes_table_comments.c.id_comments == self.id).count() 


    def coin_dislikes(self,):
        return db.session.query(dislikes_table_comments).filter(dislikes_table_comments.c.id_comments == self.id).count() 


class PrivateMessages(db.Model):

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), index=True)
    body = db.Column(db.Text)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    recipient_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime, index=True, default=datetime.utcnow)


    def select_messages_to_dialog(user):
        """This method return dialog current_user from selected user"""
        return db.session.query(PrivateMessages).filter(or_(and_(PrivateMessages.sender_id == current_user.id, PrivateMessages.recipient_id==user.id), and_(PrivateMessages.recipient_id == current_user.id, PrivateMessages.sender_id==user.id))).order_by(desc(PrivateMessages.timestamp))


@login.user_loader
def load_user(id):
    return User.query.get(int(id))

