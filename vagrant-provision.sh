#!/bin/bash

set -x

python=/usr/local/bin/python2.7
pip=/usr/local/bin/pip
virtualenv=/usr/local/bin/virtualenv

if ! [ -x ${python} ]
then
    echo modern Python 2
    yum install -y "@Development tools" bzip2-devel db4-devel gdbm-devel libpcap-devel ncurses-devel openssl-devel readline-devel sqlite-devel tk-devel zlib-devel
    (
        cd /usr/local/src
        # There's nothing terribly special about this version of
        # python, except that it's new enough for libres, and I've
        # used it before and trust it
        curl --silent --location https://github.com/python/cpython/archive/67064b9d921d05c9deff8999ceb21e16c4099e29.zip > python.zip
        unzip python.zip
        cd cpython-67064b9d921d05c9deff8999ceb21e16c4099e29
        ./configure --prefix=/usr/local --enable-unicode=ucs4 --enable-shared LDFLAGS="-Wl,-rpath /usr/local/lib"
        make && make altinstall
    )
fi

if ! [ -x ${pip} ]
then
    curl --silent https://bootstrap.pypa.io/get-pip.py > /tmp/get-pip.py
    ${python} /tmp/get-pip.py
fi

if ! [ -x ${virtualenv} ]
then
    ${pip} install virtualenv
fi

if ! [ -d ~vagrant/venv ]
then
    ${virtualenv} ~vagrant/venv
    chown -R vagrant:vagrant ~vagrant/venv
fi

if ! [ -r /etc/yum.repos.d/pgdg-94-centos.repo ]
then
    yum -y install http://yum.postgresql.org/9.4/redhat/rhel-6-x86_64/pgdg-centos94-9.4-1.noarch.rpm
fi

yum install -y postgresql94-server postgresql94-devel

cat <<'EOF'

Now do something like this:

[vagrant@localhost ~]$ source $HOME/venv/bin/activate
(venv)[vagrant@localhost ~]$ cd /vagrant
(venv)[vagrant@localhost vagrant]$ PATH=/usr/pgsql-9.4/bin/:$PATH 
(venv)[vagrant@localhost vagrant]$ python setup.py develop
(venv)[vagrant@localhost vagrant]$ cd examples/flask
(venv)[vagrant@localhost flask]$ pip install -r requirements.txt
(venv)[vagrant@localhost flask]$ python run.py 

... and point your browser at http://localhost:5000

EOF
