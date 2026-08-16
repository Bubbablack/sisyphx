<?php

class Service
{
    public function charge(int $amountCents): bool
    {
        $result = $this->gateway->charge($amountCents); // REVIEW: no idempotency key, double-charge risk?

        return $result;
    }
}
