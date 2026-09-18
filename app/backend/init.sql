CREATE TABLE IF NOT EXISTS orders (
    id SERIAL PRIMARY KEY,
    customer_name TEXT NOT NULL,
    item TEXT NOT NULL,
    quantity INT NOT NULL,
    created_at TIMESTAMP DEFAULT now()
);
