ALTER TABLE users
ADD CONSTRAINT users_tg_id_unique UNIQUE (tg_id);