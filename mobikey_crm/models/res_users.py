import re

from odoo import models


COPY_SUFFIX = re.compile(r' \(copy(?: \d+)?\)$')


class ResUsers(models.Model):
    _inherit = 'res.users'

    def _next_copy_login(self):
        self.ensure_one()
        # Serialize user duplication so two concurrent copies cannot choose the same login.
        self.env.cr.execute(
            'SELECT pg_advisory_xact_lock(hashtext(%s))',
            ['mobikey.res.users.copy.login'],
        )
        base_login = COPY_SUFFIX.sub('', self.login or '').strip() or 'user'
        candidate = f'{base_login} (copy)'
        sequence = 2
        Users = self.with_context(active_test=False).sudo()
        while Users.search_count([('login', '=', candidate)]):
            candidate = f'{base_login} (copy {sequence})'
            sequence += 1
        return candidate

    def copy(self, default=None):
        self.ensure_one()
        values = dict(default or {})
        if 'login' not in values:
            values['login'] = self._next_copy_login()
        return super().copy(values)
