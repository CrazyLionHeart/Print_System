#!/usr/bin/env python
# -*- coding: utf-8 -*-

try:
    from app import app
except ImportError as e:
    raise e

if __name__ == '__main__':
    app.run(debug=True)
